"""
Normalization utilities.

These are deliberately self-contained (no network, no heavyweight phone-number
database) so the pipeline has zero external runtime dependencies beyond the
extraction libraries. Documented as a known limitation in the design doc:
phone normalization is heuristic, not a full libphonenumber-grade validator.
"""
import re
import unicodedata
from datetime import datetime
from typing import Optional

# --- Skill canonicalization -------------------------------------------------

# alias -> canonical name. Extend freely; this is intentionally small + explicit
# rather than a fuzzy-matched ML model, so behavior is deterministic and auditable.
SKILL_ALIASES = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python": "Python",
    "python3": "Python",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "golang": "Go",
    "go": "Go",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "sql": "SQL",
    "c++": "C++",
    "c#": "C#",
    "html": "HTML",
    "css": "CSS",
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "graphql": "GraphQL",
    "docker": "Docker",
    "java": "Java",
}


def canonicalize_skill(raw: str) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    key = raw.strip().lower()
    key = re.sub(r"\s+", " ", key)
    if key in SKILL_ALIASES:
        return SKILL_ALIASES[key]
    if key.upper() == key.replace(" ", "").upper() and len(key) <= 5 and key.isalpha():
        return raw.strip().upper()
    return " ".join(w.capitalize() for w in key.split(" "))


# --- Phone normalization (heuristic E.164) ----------------------------------

_DEFAULT_COUNTRY_CODE = "1"  # assume NANP (US/Canada) for bare 10-digit numbers


def normalize_phone(raw: str) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if not digits:
        return None
    if digits.startswith("+"):
        digits = "+" + re.sub(r"\D", "", digits[1:])
        num = digits[1:]
        if 7 <= len(num) <= 15:
            return digits
        return None
    digits = re.sub(r"\D", "", digits)
    if len(digits) == 10:
        return f"+{_DEFAULT_COUNTRY_CODE}{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if 10 <= len(digits) <= 15:
        return f"+{digits}"
    return None


# --- Date normalization (YYYY-MM) -------------------------------------------

_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}


def normalize_date_to_year_month(raw: str) -> Optional[str]:
    """Best-effort normalize a date-ish string to YYYY-MM. Returns None if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower() in ("present", "current", "now", "ongoing", ""):
        return None

    m = re.match(r"^(\d{4})[-/](\d{1,2})$", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    m = re.match(r"^(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-01"

    m = re.match(r"^([A-Za-z]{3,9})[\s\-,]+(\d{4})$", raw)
    if m:
        mon_key = m.group(1).lower()
        for k in _MONTHS:
            if mon_key.startswith(k):
                return f"{m.group(2)}-{_MONTHS[k]}"

    m = re.match(r"^(\d{1,2})/(\d{4})$", raw)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            continue

    return None


# --- Misc --------------------------------------------------------------------

def normalize_email(raw: str) -> Optional[str]:
    if not raw:
        return None
    e = raw.strip().lower()
    if "@" not in e or "." not in e.split("@")[-1]:
        return None
    return e


def normalize_name(raw: str) -> Optional[str]:
    if not raw:
        return None
    name = unicodedata.normalize("NFKC", raw).strip()
    name = re.sub(r"\s+", " ", name)
    return name if name else None


def normalize_country(raw: str) -> Optional[str]:
    """Map common country forms to ISO-3166 alpha-2. Small explicit table by design."""
    if not raw:
        return None
    key = raw.strip().lower()
    table = {
        "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
        "india": "IN", "in": "IN",
        "uk": "GB", "united kingdom": "GB", "great britain": "GB",
        "canada": "CA", "ca": "CA",
        "germany": "DE", "deutschland": "DE",
        "france": "FR",
        "australia": "AU",
    }
    if key in table:
        return table[key]
    if len(raw.strip()) == 2:
        return raw.strip().upper()
    return None
