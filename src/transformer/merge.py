"""
Merge stage.

Policy (documented here because it's the heart of the design):

1. MATCH KEY: two source-records are the same candidate if they share a
   normalized email OR a normalized phone OR a normalized full name
   (case/space-insensitive). Email is the strongest signal, phone next,
   name weakest (collisions possible) — but for this assignment's scale
   and lack of a true identity-resolution model, any shared key merges.
   We use union-find so transitive matches (A-B share email, B-C share
   phone) end up in one group.

2. WINNER SELECTION (scalar fields: full_name, headline, city/region/
   country, years_experience, links): among all candidate values for a
   field, pick the one with the highest *post-corroboration* confidence.
   Ties broken by source priority: recruiter_csv/ats_json (structured) >
   resume > notes. This reflects "structured systems of record beat
   prose," a defensible recruiting-data default.

3. CORROBORATION BOOST: if two-or-more sources independently produced the
   *same normalized value* for a field, that value's confidence is boosted
   (+0.12 per additional corroborating source, capped at 0.97). Disagreeing
   values do not affect each other's confidence — we don't punish a
   correct-but-lonely source, we just don't reward it either.

4. LIST FIELDS (emails, phones, skills, links.other): union of all
   normalized values across sources, deduped, each tagged with the full
   list of sources that produced it.

5. EXPERIENCE / EDUCATION: dedup loosely by (company, title) /
   (institution, degree) pairs (case-insensitive); entries that don't
   match anything are kept as separate roles/degrees. Provenance is
   attached per entry, not merged-away.

6. OVERALL CONFIDENCE: mean of the confidences of all top-level fields
   that ended up populated (missing fields don't drag the average down —
   "honestly empty" is not "wrong").
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .models import CandidateRecord, ValueWithProvenance
from . import normalize as norm


def _source_priority(source_name: str) -> int:
    for prefix, pri in (("recruiter_csv", 0), ("ats_json", 0), ("resume", 1), ("notes", 2)):
        if source_name.startswith(prefix):
            return pri
    return 3


class _UnionFind:
    def __init__(self):
        self.parent: Dict[int, int] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _norm_email_key(rec: CandidateRecord) -> Optional[str]:
    for e in rec.emails:
        n = norm.normalize_email(e.value)
        if n:
            return n
    return None


def _norm_phone_key(rec: CandidateRecord) -> Optional[str]:
    for p in rec.phones:
        n = norm.normalize_phone(p.value)
        if n:
            return n
    return None


def _norm_name_key(rec: CandidateRecord) -> Optional[str]:
    if rec.full_name:
        n = norm.normalize_name(rec.full_name.value)
        if n:
            return n.lower()
    return None


def group_records(records: List[CandidateRecord]) -> List[List[CandidateRecord]]:
    """Union-find grouping by shared email/phone/name keys."""
    uf = _UnionFind()
    email_idx: Dict[str, int] = {}
    phone_idx: Dict[str, int] = {}
    name_idx: Dict[str, int] = {}

    for i, rec in enumerate(records):
        uf.find(i)
        ek, pk, nk = _norm_email_key(rec), _norm_phone_key(rec), _norm_name_key(rec)
        if ek:
            if ek in email_idx:
                uf.union(i, email_idx[ek])
            else:
                email_idx[ek] = i
        if pk:
            if pk in phone_idx:
                uf.union(i, phone_idx[pk])
            else:
                phone_idx[pk] = i
        if nk:
            if nk in name_idx:
                uf.union(i, name_idx[nk])
            else:
                name_idx[nk] = i

    groups: Dict[int, List[CandidateRecord]] = defaultdict(list)
    for i, rec in enumerate(records):
        groups[uf.find(i)].append(rec)
    return list(groups.values())


def _resolve_scalar(values: List[ValueWithProvenance], normalizer=None):
    """Pick a winner among competing scalar values; return (winner_vwp, confidence, all_sources)."""
    if not values:
        return None, 0.0, []

    buckets: Dict[str, List[ValueWithProvenance]] = defaultdict(list)
    for v in values:
        key = normalizer(v.value) if normalizer else str(v.value).strip().lower()
        if key is None:
            continue
        buckets[key].append(v)

    if not buckets:
        return None, 0.0, []

    best_key, best_conf = None, -1.0
    for key, vwps in buckets.items():
        base = max(v.confidence for v in vwps)
        n_sources = len({v.source for v in vwps})
        boosted = min(0.97, base + 0.12 * (n_sources - 1))
        if best_key is None or boosted > best_conf or (
            boosted == best_conf
            and min(_source_priority(v.source) for v in vwps) < min(_source_priority(v.source) for v in buckets[best_key])
        ):
            best_key, best_conf = key, boosted

    best_sources = buckets[best_key]
    chosen_vwp = sorted(best_sources, key=lambda v: (_source_priority(v.source), -v.confidence))[0]
    return chosen_vwp, best_conf, sorted({v.source for v in best_sources})


def _merge_list(values: List[ValueWithProvenance], normalizer=None) -> List[dict]:
    buckets: Dict[str, List[ValueWithProvenance]] = defaultdict(list)
    order: List[str] = []
    for v in values:
        key = normalizer(v.value) if normalizer else (str(v.value).strip().lower() if v.value else None)
        if not key:
            continue
        if key not in buckets:
            order.append(key)
        buckets[key].append(v)

    out = []
    for key in order:
        vwps = buckets[key]
        base = max(v.confidence for v in vwps)
        n_sources = len({v.source for v in vwps})
        conf = min(0.97, base + 0.12 * (n_sources - 1))
        # When a normalizer is supplied (email/phone/skill), the normalized form
        # IS the canonical display value we want in the output (E.164 phone,
        # lowercase email, canonical skill name) — not the raw source string.
        display_value = key if normalizer else \
            sorted(vwps, key=lambda v: (_source_priority(v.source), -v.confidence))[0].value
        out.append({
            "value": display_value,
            "normalized": key,
            "confidence": round(conf, 2),
            "sources": sorted({v.source for v in vwps}),
        })
    return out


def _merge_dict_list(values: List[ValueWithProvenance], match_keys: Tuple[str, ...]) -> List[dict]:
    """Loosely dedup list-of-dict fields (experience/education) by match_keys."""
    buckets: Dict[Tuple, List[ValueWithProvenance]] = defaultdict(list)
    order: List[Tuple] = []
    for v in values:
        d = v.value
        key = tuple((str(d.get(k) or "")).strip().lower() for k in match_keys)
        if key not in buckets:
            order.append(key)
        buckets[key].append(v)

    out = []
    for key in order:
        vwps = buckets[key]
        merged: dict = {}
        for v in sorted(vwps, key=lambda v: _source_priority(v.source)):
            for k, val in v.value.items():
                if k.startswith("_"):
                    continue
                if val and not merged.get(k):
                    merged[k] = val
        base = max(v.confidence for v in vwps)
        n_sources = len({v.source for v in vwps})
        merged["_confidence"] = round(min(0.97, base + 0.12 * (n_sources - 1)), 2)
        merged["_sources"] = sorted({v.source for v in vwps})
        out.append(merged)
    return out


def merge_group(group: List[CandidateRecord]) -> dict:
    """Merge one group (same candidate, multiple sources) into a merged-field dict
    consumed by the projection stage. Output uses internal keys; projection maps
    these onto the requested output schema."""

    all_emails = [v for r in group for v in r.emails]
    all_phones = [v for r in group for v in r.phones]
    all_skills = [v for r in group for v in r.skills]
    all_exp = [v for r in group for v in r.experience]
    all_edu = [v for r in group for v in r.education]

    name_vals = [r.full_name for r in group if r.full_name]
    headline_vals = [r.headline for r in group if r.headline]
    city_vals = [r.city for r in group if r.city]
    region_vals = [r.region for r in group if r.region]
    country_vals = [r.country for r in group if r.country]
    yoe_vals = [r.years_experience for r in group if r.years_experience]
    li_vals = [r.linkedin for r in group if r.linkedin]
    gh_vals = [r.github for r in group if r.github]
    pf_vals = [r.portfolio for r in group if r.portfolio]

    name_winner, name_conf, name_sources = _resolve_scalar(name_vals, norm.normalize_name)
    headline_winner, headline_conf, headline_sources = _resolve_scalar(headline_vals)
    city_winner, city_conf, city_sources = _resolve_scalar(city_vals)
    region_winner, region_conf, region_sources = _resolve_scalar(region_vals)
    country_winner, country_conf, country_sources = _resolve_scalar(country_vals, norm.normalize_country)
    yoe_winner, yoe_conf, yoe_sources = _resolve_scalar(yoe_vals)
    li_winner, li_conf, li_sources = _resolve_scalar(li_vals)
    gh_winner, gh_conf, gh_sources = _resolve_scalar(gh_vals)
    pf_winner, pf_conf, pf_sources = _resolve_scalar(pf_vals)

    merged = {
        "full_name": {"value": name_winner.value if name_winner else None,
                      "confidence": name_conf, "sources": name_sources},
        "emails": _merge_list(all_emails, norm.normalize_email),
        "phones": _merge_list(all_phones, norm.normalize_phone),
        "city": {"value": city_winner.value if city_winner else None,
                 "confidence": city_conf, "sources": city_sources},
        "region": {"value": region_winner.value if region_winner else None,
                   "confidence": region_conf, "sources": region_sources},
        "country": {"value": norm.normalize_country(country_winner.value) if country_winner else None,
                    "confidence": country_conf, "sources": country_sources},
        "linkedin": {"value": li_winner.value if li_winner else None,
                     "confidence": li_conf, "sources": li_sources},
        "github": {"value": gh_winner.value if gh_winner else None,
                   "confidence": gh_conf, "sources": gh_sources},
        "portfolio": {"value": pf_winner.value if pf_winner else None,
                      "confidence": pf_conf, "sources": pf_sources},
        "headline": {"value": headline_winner.value if headline_winner else None,
                     "confidence": headline_conf, "sources": headline_sources},
        "years_experience": {"value": yoe_winner.value if yoe_winner else None,
                              "confidence": yoe_conf, "sources": yoe_sources},
        "skills": _merge_list(all_skills, norm.canonicalize_skill),
        "experience": _merge_dict_list(all_exp, ("company", "title")),
        "education": _merge_dict_list(all_edu, ("institution", "degree")),
        "_source_records": [r.source_name for r in group],
    }
    return merged
