"""Detect stage: figure out which extractor a given input path needs.

Detection is by extension first (cheap, deterministic), falling back to a
light content sniff for ambiguous .txt files (recruiter notes vs. plain-text
resume) using a couple of header keywords. Anything unrecognized is reported
as 'unknown' and skipped with a warning rather than crashing the run.
"""
import json
from typing import Tuple

from . import normalize  # noqa: F401  (kept for symmetry / future use)


def detect_source_kind(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".csv"):
        return "recruiter_csv"
    if lower.endswith(".json"):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
            return "ats_json"
        except Exception:
            return "ats_json"  # still route there; extractor handles garbage gracefully
    if lower.endswith(".pdf") or lower.endswith(".docx"):
        return "resume"
    if lower.endswith(".txt"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                head = f.read(500).lower()
        except FileNotFoundError:
            return "unknown"
        if any(tag in head for tag in ("name:", "candidate:", "recruiter note", "notes on")):
            return "recruiter_notes"
        return "resume"  # plain prose .txt defaults to resume-style extraction
    return "unknown"
