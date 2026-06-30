"""Extractor for resume files (unstructured source): .pdf, .docx, .txt.

Resumes are free-text, so extraction here is regex/heuristic based and
intentionally conservative: we only emit a field when we're reasonably
confident, and everything gets a lower base confidence than structured
sources by design (see BASE_CONFIDENCE).
"""
import re
from typing import List, Optional

from ..models import CandidateRecord, ValueWithProvenance, BASE_CONFIDENCE
from .. import normalize as norm

SOURCE_TYPE = "unstructured"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\-\.\(\)\s]{8,}\d)")
LINKEDIN_RE = re.compile(r"(https?://)?(www\.)?linkedin\.com/in/[A-Za-z0-9\-_/]+", re.I)
GITHUB_RE = re.compile(r"(https?://)?(www\.)?github\.com/[A-Za-z0-9\-_/]+", re.I)


def _read_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except Exception:
            return ""
    if path.lower().endswith(".docx"):
        try:
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            return ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _find_section(text: str, header_aliases) -> Optional[str]:
    """Grab the text block following a section header until the next header-like line."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        clean = line.strip().lower().rstrip(":")
        if clean in header_aliases:
            block = []
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt and nxt.lower().rstrip(":") in (
                    "experience", "work experience", "education", "skills",
                    "projects", "summary", "certifications",
                ):
                    break
                block.append(lines[j])
            return "\n".join(block).strip()
    return None


def extract(path: str) -> List[CandidateRecord]:
    text = _read_text(path)
    if not text.strip():
        return []  # unreadable/garbage/missing file -> degrade gracefully, no record

    conf = BASE_CONFIDENCE["resume_text"]
    src_name = f"resume:{path.split('/')[-1]}"
    rec = CandidateRecord(source_name=src_name, source_type=SOURCE_TYPE)

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        # Heuristic: first non-empty line is the name if it looks name-like
        # (2-4 capitalized words, no digits/@ symbol).
        if (1 < len(first.split()) <= 4 and "@" not in first
                and not any(ch.isdigit() for ch in first)):
            rec.full_name = ValueWithProvenance(first, src_name, "first_line_heuristic", conf)

    emails = EMAIL_RE.findall(text)
    if emails:
        rec.emails.append(ValueWithProvenance(emails[0], src_name, "regex_extract", conf))

    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if 10 <= len(digits) <= 15:
            rec.phones.append(ValueWithProvenance(m.group(1), src_name, "regex_extract", conf))
            break

    li = LINKEDIN_RE.search(text)
    if li:
        url = li.group(0)
        rec.linkedin = ValueWithProvenance(
            url if url.startswith("http") else "https://" + url, src_name, "regex_extract", conf)

    gh = GITHUB_RE.search(text)
    if gh:
        url = gh.group(0)
        rec.github = ValueWithProvenance(
            url if url.startswith("http") else "https://" + url, src_name, "regex_extract", conf)

    skills_block = _find_section(text, {"skills", "technical skills", "core skills"})
    if skills_block:
        for tok in re.split(r"[,;\u2022\n\|]", skills_block):
            tok = tok.strip("- \t")
            if tok and len(tok) <= 40:
                rec.skills.append(ValueWithProvenance(tok, src_name, "section_parse", conf))

    summary_block = _find_section(text, {"summary", "professional summary", "objective"})
    if summary_block:
        rec.headline = ValueWithProvenance(
            summary_block.split("\n")[0][:140], src_name, "section_parse", conf * 0.8)

    return [rec]
