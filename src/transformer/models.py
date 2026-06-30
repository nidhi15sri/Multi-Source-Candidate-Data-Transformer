"""
Internal canonical record model.

This is intentionally richer than the default *output* schema: every scalar
and list item is wrapped with provenance (which source, which extraction
method) so the merge stage can resolve conflicts and the projection stage
can decide what to expose. The default-output projection is just one
"view" of this internal record.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ValueWithProvenance:
    value: Any
    source: str          # e.g. "recruiter_csv", "ats_json", "resume:john.pdf", "notes:notes.txt"
    method: str          # e.g. "direct_field", "regex_extract", "header_parse"
    confidence: float    # 0..1, source/method-intrinsic confidence (pre-merge)


@dataclass
class CandidateRecord:
    """One source's view of one candidate, before merging across sources."""
    full_name: Optional[ValueWithProvenance] = None
    emails: List[ValueWithProvenance] = field(default_factory=list)
    phones: List[ValueWithProvenance] = field(default_factory=list)
    city: Optional[ValueWithProvenance] = None
    region: Optional[ValueWithProvenance] = None
    country: Optional[ValueWithProvenance] = None
    linkedin: Optional[ValueWithProvenance] = None
    github: Optional[ValueWithProvenance] = None
    portfolio: Optional[ValueWithProvenance] = None
    other_links: List[ValueWithProvenance] = field(default_factory=list)
    headline: Optional[ValueWithProvenance] = None
    years_experience: Optional[ValueWithProvenance] = None
    skills: List[ValueWithProvenance] = field(default_factory=list)  # value = skill name
    experience: List[ValueWithProvenance] = field(default_factory=list)  # value = dict
    education: List[ValueWithProvenance] = field(default_factory=list)   # value = dict

    # bookkeeping
    source_name: str = ""
    source_type: str = ""  # "structured" | "unstructured"


# Base confidence by source type/method. Structured, schema'd sources are more
# trustworthy than text mined from prose. These are starting priors; the merge
# stage adjusts them further based on cross-source agreement.
BASE_CONFIDENCE = {
    "recruiter_csv": 0.85,
    "ats_json": 0.85,
    "resume_text": 0.55,
    "recruiter_notes": 0.45,
}
