"""
Validation stage.

Validates the *projected* output (default profile or custom-config output)
before it's returned. Validation failures are collected, not raised, so a
bad/missing source degrades the run instead of crashing it — per the
"robust" constraint in the spec. The CLI decides whether to fail the run
based on severity (errors vs warnings).
"""
from typing import List


REQUIRED_DEFAULT_FIELDS = ["candidate_id", "full_name"]


def validate_default_profile(profile: dict) -> List[str]:
    errors = []
    for f in REQUIRED_DEFAULT_FIELDS:
        if not profile.get(f):
            errors.append(f"missing or empty required field: {f}")

    if not isinstance(profile.get("emails", []), list):
        errors.append("emails must be a list")
    if not isinstance(profile.get("phones", []), list):
        errors.append("phones must be a list")
    if not isinstance(profile.get("skills", []), list):
        errors.append("skills must be a list")

    conf = profile.get("overall_confidence")
    if conf is not None and not (0 <= conf <= 1):
        errors.append(f"overall_confidence out of range [0,1]: {conf}")

    for p in profile.get("phones", []):
        if p and not p.startswith("+"):
            errors.append(f"phone not in E.164 form: {p}")

    for exp in profile.get("experience", []):
        for k in ("start", "end"):
            v = exp.get(k)
            if v and not (len(v) == 7 and v[4] == "-"):
                errors.append(f"experience.{k} not in YYYY-MM form: {v}")

    return errors


def validate_against_config(output: dict, config: dict) -> List[str]:
    """Validate a custom-projected output: every requested 'required' field
    must be present and non-null unless on_missing == 'omit' was honored."""
    errors = []
    on_missing = config.get("on_missing", "null")
    for field_spec in config.get("fields", []):
        if not field_spec.get("required"):
            continue
        path = field_spec["path"]
        cur = output
        found = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                found = False
                break
        if not found:
            if on_missing != "omit":
                errors.append(f"required field missing from output: {path}")
        elif cur is None and on_missing == "error":
            errors.append(f"required field is null (on_missing=error): {path}")
    return errors
