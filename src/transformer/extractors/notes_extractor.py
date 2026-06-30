"""Extractor for recruiter notes (.txt free text) — unstructured source.

Notes are the least structured, most opinion-laden source, so they get the
lowest base confidence. We still mine contact info / skill mentions if
present, and we fold the raw note text in as an experience-adjacent
"summary" signal rather than fabricating structured experience entries —
recruiter notes rarely contain reliable start/end dates.
"""
import re
from typing import List

from ..models import CandidateRecord, ValueWithProvenance, BASE_CONFIDENCE
from .resume_extractor import EMAIL_RE, PHONE_RE

SOURCE_TYPE = "unstructured"

# Looks for "Name: ..." or "Candidate: ..." style headers some recruiters use.
NAME_LINE_RE = re.compile(r"^(name|candidate)\s*[:\-]\s*(.+)$", re.I | re.M)

# A small explicit skill-mention vocabulary so we don't hallucinate skills
# from prose. Anything not in here is left out (deliberate scope cut).
KNOWN_SKILL_MENTIONS = [
    "python", "javascript", "react", "node", "java", "go", "sql", "aws",
    "gcp", "kubernetes", "docker", "typescript", "machine learning", "ml",
]


def extract(path: str) -> List[CandidateRecord]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    if not text.strip():
        return []

    conf = BASE_CONFIDENCE["recruiter_notes"]
    src_name = f"notes:{path.split('/')[-1]}"
    rec = CandidateRecord(source_name=src_name, source_type=SOURCE_TYPE)

    name_match = NAME_LINE_RE.search(text)
    if name_match:
        rec.full_name = ValueWithProvenance(name_match.group(2).strip(), src_name, "labeled_line", conf)

    emails = EMAIL_RE.findall(text)
    if emails:
        rec.emails.append(ValueWithProvenance(emails[0], src_name, "regex_extract", conf))

    phone_match = PHONE_RE.search(text)
    if phone_match:
        digits = re.sub(r"\D", "", phone_match.group(1))
        if 10 <= len(digits) <= 15:
            rec.phones.append(ValueWithProvenance(phone_match.group(1), src_name, "regex_extract", conf))

    lower = text.lower()
    for skill in KNOWN_SKILL_MENTIONS:
        if re.search(r"\b" + re.escape(skill) + r"\b", lower):
            rec.skills.append(ValueWithProvenance(skill, src_name, "keyword_match", conf))

    # First line often is a one-line recruiter take; surface it as a headline
    # candidate only (low confidence) since it's opinion, not the candidate's own words.
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), None)
    if first_line and not name_match:
        rec.headline = ValueWithProvenance(first_line[:140], src_name, "first_line_heuristic", conf * 0.6)

    return [rec]
