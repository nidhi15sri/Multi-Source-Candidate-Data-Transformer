"""Extractor for ATS JSON blobs (structured source).

ATS systems use their own field names. This extractor maps a representative
schema to our canonical fields.

Expected shape (illustrative):
[
  {
    "candidate_name": "...",
    "contact": {"email_address": "...", "mobile": "..."},
    "current_role": {"employer": "...", "job_title": "..."},
    "work_history": [{"employer": "...", "job_title": "...", "from": "...", "to": "...", "desc": "..."}],
    "schools": [{"name": "...", "degree_name": "...", "field_of_study": "...", "grad_year": "..."}],
    "tags": ["python", "react"]
  },
  ...
]
"""
import json
from typing import List

from ..models import CandidateRecord, ValueWithProvenance, BASE_CONFIDENCE

SOURCE_TYPE = "structured"


def extract(path: str) -> List[CandidateRecord]:
    records: List[CandidateRecord] = []
    conf = BASE_CONFIDENCE["ats_json"]
    src_name = f"ats_json:{path.split('/')[-1]}"

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return records  # missing or garbage source -> degrade gracefully

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return records

    for item in data:
        if not isinstance(item, dict):
            continue
        rec = CandidateRecord(source_name=src_name, source_type=SOURCE_TYPE)

        name = item.get("candidate_name") or item.get("name")
        if name:
            rec.full_name = ValueWithProvenance(name, src_name, "direct_field", conf)

        contact = item.get("contact", {}) or {}
        email = contact.get("email_address") or contact.get("email")
        if email:
            rec.emails.append(ValueWithProvenance(email, src_name, "direct_field", conf))
        mobile = contact.get("mobile") or contact.get("phone")
        if mobile:
            rec.phones.append(ValueWithProvenance(mobile, src_name, "direct_field", conf))

        current = item.get("current_role", {}) or {}
        if current.get("job_title"):
            rec.headline = ValueWithProvenance(current["job_title"], src_name, "direct_field", conf)

        for wh in item.get("work_history", []) or []:
            if not isinstance(wh, dict):
                continue
            rec.experience.append(ValueWithProvenance(
                {
                    "company": wh.get("employer"),
                    "title": wh.get("job_title"),
                    "start": wh.get("from"),
                    "end": wh.get("to"),
                    "summary": wh.get("desc"),
                    "_current": (wh.get("to") in (None, "", "present", "Present")),
                },
                src_name, "direct_field", conf,
            ))

        for sc in item.get("schools", []) or []:
            if not isinstance(sc, dict):
                continue
            rec.education.append(ValueWithProvenance(
                {
                    "institution": sc.get("name"),
                    "degree": sc.get("degree_name"),
                    "field": sc.get("field_of_study"),
                    "end_year": sc.get("grad_year"),
                },
                src_name, "direct_field", conf,
            ))

        for tag in item.get("tags", []) or []:
            rec.skills.append(ValueWithProvenance(tag, src_name, "direct_field", conf))

        records.append(rec)

    return records
