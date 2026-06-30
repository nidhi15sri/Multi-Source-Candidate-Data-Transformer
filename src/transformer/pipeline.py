"""
Pipeline orchestrator.

ingest -> parse -> standardize -> reconcile (match + resolve) -> score ->
shape -> verify.

"Reconcile" is deliberately split into two functions rather than one
"merge" step: group_records() answers "which records are the same person"
(identity resolution), merge_group() answers "which value wins when
sources disagree" (conflict resolution). Confidence ("score") is computed
as part of reconcile but treated as its own named concern since it's a
first-class output, not an implementation detail.

Deterministic: same inputs (and same file ordering) always produce the same
output, because every stage is pure functions over the inputs with no
randomness, no wall-clock dependence (except candidate_id generation, which
is a stable hash of merged identity, not a timestamp/uuid4).
"""
import hashlib
import warnings as _warn
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import detect
from .extractors import csv_extractor, json_extractor, resume_extractor, notes_extractor
from .merge import group_records, merge_group
from .project import build_default_profile, apply_config
from .validate import validate_default_profile, validate_against_config


EXTRACTOR_MAP = {
    "recruiter_csv": csv_extractor.extract,
    "ats_json": json_extractor.extract,
    "resume": resume_extractor.extract,
    "recruiter_notes": notes_extractor.extract,
}


@dataclass
class RunResult:
    profiles: List[dict]
    custom_outputs: List[dict]
    warnings: List[str]
    errors: List[str]


def _stable_candidate_id(merged: dict) -> str:
    """Deterministic id from the strongest available identity signal, so
    re-running the pipeline on the same inputs yields the same candidate_id."""
    basis = None
    if merged["emails"]:
        basis = "email:" + merged["emails"][0]["normalized"]
    elif merged["phones"]:
        basis = "phone:" + merged["phones"][0]["normalized"]
    elif merged["full_name"]["value"]:
        basis = "name:" + merged["full_name"]["value"].strip().lower()
    else:
        basis = "anon:" + ",".join(sorted(merged["_source_records"]))
    h = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    return f"cand_{h}"


def run(input_paths: List[str], config: Optional[dict] = None) -> RunResult:
    warnings: List[str] = []
    errors: List[str] = []
    all_records = []

    for path in input_paths:
        kind = detect.detect_source_kind(path)
        if kind == "unknown":
            warnings.append(f"skipped unrecognized source (unsupported file type): {path}")
            continue
        extractor = EXTRACTOR_MAP[kind]
        try:
            recs = extractor(path)
        except Exception as e:  # noqa: BLE001 - never let one bad source crash the run
            warnings.append(f"source failed to parse, degraded to empty ({kind}): {path} ({e})")
            recs = []
        if not recs:
            warnings.append(f"source produced no usable records (missing/empty/garbage?): {path}")
        all_records.extend(recs)

    if not all_records:
        errors.append("no usable records extracted from any source")
        return RunResult([], [], warnings, errors)

    groups = group_records(all_records)
    # Stable ordering: sort groups by their best available identity key so
    # output order doesn't depend on dict/set iteration order.
    def group_sort_key(group):
        m = merge_group(group)
        return _stable_candidate_id(m)

    profiles = []
    custom_outputs = []
    for group in groups:
        merged = merge_group(group)
        cand_id = _stable_candidate_id(merged)
        profile = build_default_profile(cand_id, merged)
        verrs = validate_default_profile(profile)
        if verrs:
            warnings.extend(f"[{cand_id}] {e}" for e in verrs)
        profiles.append(profile)

        if config:
            custom = apply_config(profile, config)
            cerrs = validate_against_config(custom, config)
            if cerrs:
                warnings.extend(f"[{cand_id}] custom-output: {e}" for e in cerrs)
            custom_outputs.append(custom)

    profiles.sort(key=lambda p: p["candidate_id"])
    custom_outputs.sort(key=lambda c: str(c.get("candidate_id", "")))

    return RunResult(profiles, custom_outputs, warnings, errors)
