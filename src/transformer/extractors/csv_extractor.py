"""Extractor for recruiter CSV exports (structured source).

Expected columns (case-insensitive, order-independent): name, email, phone,
current_company, title. Extra columns are ignored; missing columns degrade
gracefully (field simply absent from this source's record).
"""
import csv
from typing import List

from ..models import CandidateRecord, ValueWithProvenance, BASE_CONFIDENCE

SOURCE_TYPE = "structured"


def extract(path: str) -> List[CandidateRecord]:
    records = []
    conf = BASE_CONFIDENCE["recruiter_csv"]
    src_name = f"recruiter_csv:{path.split('/')[-1]}"

    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return records
            norm_fields = {fn.strip().lower(): fn for fn in reader.fieldnames}

            for row in reader:
                rec = CandidateRecord(source_name=src_name, source_type=SOURCE_TYPE)

                def get(*keys):
                    for k in keys:
                        real = norm_fields.get(k)
                        if real and row.get(real, "").strip():
                            return row[real].strip()
                    return None

                name = get("name", "full_name")
                if name:
                    rec.full_name = ValueWithProvenance(name, src_name, "direct_field", conf)

                email = get("email")
                if email:
                    rec.emails.append(ValueWithProvenance(email, src_name, "direct_field", conf))

                phone = get("phone")
                if phone:
                    rec.phones.append(ValueWithProvenance(phone, src_name, "direct_field", conf))

                company = get("current_company", "company")
                title = get("title")
                if company or title:
                    rec.experience.append(ValueWithProvenance(
                        {"company": company, "title": title, "start": None, "end": None,
                         "summary": None, "_current": True},
                        src_name, "direct_field", conf,
                    ))
                    if title:
                        rec.headline = ValueWithProvenance(title, src_name, "derived_from_title", conf * 0.9)

                records.append(rec)
    except FileNotFoundError:
        return records  # missing source -> degrade gracefully, no records
    except csv.Error:
        return records  # garbage/malformed CSV -> degrade gracefully

    return records
