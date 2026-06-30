"""
Projection stage.

Internal canonical record (produced by merge.py) -> output. There are two
projections:

  build_default_profile(): the fixed default schema from the spec.
  apply_config(): the "required twist" — reshape that default canonical
    record per a runtime config (select fields, rename/remap via "from",
    per-field normalize override, toggle provenance/confidence, choose
    missing-value behavior).

Keeping these separate enforces the architectural rule from the spec:
"keep a clean separation between your internal canonical record and a
projection layer." The internal record is the single source of truth;
config changes never touch the merge engine.
"""
import copy
from typing import Any, Dict, List, Optional

from . import normalize as norm


def build_default_profile(candidate_id: str, merged: dict) -> dict:
    """Build the fixed default-schema profile from a merged internal record."""

    provenance: List[dict] = []

    def track(field: str, sources: List[str], method: str = "merge"):
        for s in sources:
            provenance.append({"field": field, "source": s, "method": method})

    emails = [e["value"] for e in merged["emails"]]
    track("emails", sorted({s for e in merged["emails"] for s in e["sources"]}))

    phones_norm = []
    for p in merged["phones"]:
        v = norm.normalize_phone(p["value"]) or p["value"]
        phones_norm.append(v)
    track("phones", sorted({s for p in merged["phones"] for s in p["sources"]}))

    if merged["full_name"]["value"]:
        track("full_name", merged["full_name"]["sources"])
    if merged["city"]["value"] or merged["region"]["value"] or merged["country"]["value"]:
        for f in ("city", "region", "country"):
            if merged[f]["value"]:
                track(f"location.{f}", merged[f]["sources"])
    for f in ("linkedin", "github", "portfolio"):
        if merged[f]["value"]:
            track(f"links.{f}", merged[f]["sources"])
    if merged["headline"]["value"]:
        track("headline", merged["headline"]["sources"])
    if merged["years_experience"]["value"]:
        track("years_experience", merged["years_experience"]["sources"])

    skills = []
    for s in merged["skills"]:
        skills.append({"name": s["value"], "confidence": s["confidence"], "sources": s["sources"]})
        track("skills", s["sources"])

    experience = []
    for e in merged["experience"]:
        experience.append({
            "company": e.get("company"),
            "title": e.get("title"),
            "start": norm.normalize_date_to_year_month(e.get("start")) if e.get("start") else None,
            "end": norm.normalize_date_to_year_month(e.get("end")) if e.get("end") else None,
            "summary": e.get("summary"),
        })
        track("experience", e.get("_sources", []))

    education = []
    for e in merged["education"]:
        education.append({
            "institution": e.get("institution"),
            "degree": e.get("degree"),
            "field": e.get("field"),
            "end_year": e.get("end_year"),
        })
        track("education", e.get("_sources", []))

    # overall_confidence: mean of confidences of fields that are actually populated.
    field_confs = []
    for f in ("full_name", "city", "region", "country", "linkedin", "github", "portfolio",
              "headline", "years_experience"):
        if merged[f]["value"]:
            field_confs.append(merged[f]["confidence"])
    field_confs += [e["confidence"] for e in merged["emails"]]
    field_confs += [p["confidence"] for p in merged["phones"]]
    field_confs += [s["confidence"] for s in merged["skills"]]
    field_confs += [e["_confidence"] for e in merged["experience"]]
    field_confs += [e["_confidence"] for e in merged["education"]]
    overall_confidence = round(sum(field_confs) / len(field_confs), 3) if field_confs else 0.0

    profile = {
        "candidate_id": candidate_id,
        "full_name": merged["full_name"]["value"],
        "emails": emails,
        "phones": phones_norm,
        "location": {
            "city": merged["city"]["value"],
            "region": merged["region"]["value"],
            "country": merged["country"]["value"],
        },
        "links": {
            "linkedin": merged["linkedin"]["value"],
            "github": merged["github"]["value"],
            "portfolio": merged["portfolio"]["value"],
            "other": [],
        },
        "headline": merged["headline"]["value"],
        "years_experience": merged["years_experience"]["value"],
        "skills": skills,
        "experience": experience,
        "education": education,
        "provenance": provenance,
        "overall_confidence": overall_confidence,
    }
    return profile


# --- Configurable projection (the "required twist") -------------------------

def _get_path(obj: Any, path: str) -> Any:
    """Resolve a dotted/bracket path like 'emails[0]' or 'links.linkedin' against
    the default profile dict."""
    cur = obj
    for part in path.replace("]", "").split("."):
        if "[" in part:
            name, idx = part.split("[")
            cur = cur.get(name) if isinstance(cur, dict) else None
            if cur is None:
                return None
            try:
                cur = cur[int(idx)] if idx != "" else cur
            except (IndexError, ValueError):
                return None
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                return None
    return cur


def _apply_normalize(value: Any, kind: Optional[str]) -> Any:
    if value is None or kind is None:
        return value
    if kind == "E.164":
        if isinstance(value, list):
            return [norm.normalize_phone(v) for v in value]
        return norm.normalize_phone(value)
    if kind == "canonical":
        if isinstance(value, list):
            return [norm.canonicalize_skill(v) for v in value]
        return norm.canonicalize_skill(value)
    return value


def apply_config(profile: dict, config: dict) -> dict:
    """Reshape a default-schema profile per a runtime config. See SKILL/design
    doc for the config schema. No re-extraction or re-merging happens here —
    purely a read-only projection over the already-built canonical profile."""

    out: Dict[str, Any] = {}
    include_confidence = config.get("include_confidence", False)
    on_missing = config.get("on_missing", "null")  # "null" | "omit" | "error"

    skills_list = profile.get("skills", [])
    skill_names = [s["name"] for s in skills_list]

    for field_spec in config.get("fields", []):
        out_path = field_spec["path"]
        from_path = field_spec.get("from", out_path)
        required = field_spec.get("required", False)
        norm_kind = field_spec.get("normalize")

        if from_path == "skills" or from_path.startswith("skills"):
            value = skill_names if from_path in ("skills", "skills[].name") else _get_path(profile, from_path)
        else:
            value = _get_path(profile, from_path)

        value = _apply_normalize(value, norm_kind)

        if value is None or value == [] or value == "":
            if required and on_missing == "error":
                raise ValueError(f"Required field '{out_path}' (from '{from_path}') is missing.")
            if on_missing == "omit":
                continue
            value = None  # "null" policy

        _set_path(out, out_path, value)

        if include_confidence and out_path != "candidate_id":
            conf = _confidence_for(profile, from_path, skills_list)
            if conf is not None:
                _set_path(out, f"_confidence.{out_path}", conf)

    return out


def _set_path(obj: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _confidence_for(profile: dict, from_path: str, skills_list: List[dict]) -> Optional[float]:
    if from_path.startswith("skills"):
        if skills_list:
            return round(sum(s["confidence"] for s in skills_list) / len(skills_list), 2)
        return None
    if from_path == "overall_confidence" or from_path == "":
        return profile.get("overall_confidence")
    # Field-level confidence isn't tracked post-flattening for every field;
    # fall back to overall_confidence as a reasonable proxy, documented
    # as a known simplification for fields without a dedicated per-field score.
    return profile.get("overall_confidence")
