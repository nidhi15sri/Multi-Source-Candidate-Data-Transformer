import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from transformer import normalize as norm
from transformer.pipeline import run


def test_phone_normalization_e164():
    assert norm.normalize_phone("(415) 555-0199") == "+14155550199"
    assert norm.normalize_phone("+91 98765 11111") == "+919876511111"
    assert norm.normalize_phone("not a phone") is None
    assert norm.normalize_phone("") is None


def test_date_normalization():
    assert norm.normalize_date_to_year_month("Jan 2020") == "2020-01"
    assert norm.normalize_date_to_year_month("2019-09") == "2019-09"
    assert norm.normalize_date_to_year_month("present") is None
    assert norm.normalize_date_to_year_month("2017") == "2017-01"
    assert norm.normalize_date_to_year_month("garbage") is None


def test_skill_canonicalization():
    assert norm.canonicalize_skill("js") == "JavaScript"
    assert norm.canonicalize_skill("Python3") == "Python"
    assert norm.canonicalize_skill("reactjs") == "React"
    assert norm.canonicalize_skill("") is None


def test_email_normalization():
    assert norm.normalize_email("Jane.Doe@Gmail.com") == "jane.doe@gmail.com"
    assert norm.normalize_email("not-an-email") is None


HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "sample_inputs")


def test_pipeline_merges_across_structured_sources():
    result = run([
        os.path.join(SAMPLES, "recruiter_export.csv"),
        os.path.join(SAMPLES, "ats_export.json"),
    ])
    names = {p["full_name"] for p in result.profiles}
    assert "Jane Doe" in names
    jane = next(p for p in result.profiles if p["full_name"] == "Jane Doe")
    # merged from two sources -> exactly one email, provenance lists both sources
    assert jane["emails"] == ["jane.doe@gmail.com"]
    sources = {prov["source"] for prov in jane["provenance"] if prov["field"] == "full_name"}
    assert any("recruiter_csv" in s for s in sources)
    assert any("ats_json" in s for s in sources)


def test_pipeline_handles_missing_and_garbage_sources_without_crashing():
    result = run([
        os.path.join(SAMPLES, "recruiter_export.csv"),
        os.path.join(SAMPLES, "garbage_ats.json"),
        os.path.join(SAMPLES, "does_not_exist.csv"),
    ])
    assert result.errors == []  # at least one good source -> no fatal error
    assert any("garbage_ats.json" in w for w in result.warnings)
    assert any("does_not_exist.csv" in w for w in result.warnings)


def test_pipeline_all_sources_missing_produces_error_not_crash():
    result = run([os.path.join(SAMPLES, "does_not_exist.csv")])
    assert result.errors  # reported as error, not an exception
    assert result.profiles == []


def test_unstructured_resume_extraction_pdf():
    result = run([os.path.join(SAMPLES, "priya_shah_resume.pdf")])
    assert len(result.profiles) == 1
    p = result.profiles[0]
    assert p["full_name"] == "Priya Shah"
    assert "priya.shah@example.com" in p["emails"]


def test_unstructured_resume_extraction_docx():
    result = run([os.path.join(SAMPLES, "sam_okafor_resume.docx")])
    assert len(result.profiles) == 1
    p = result.profiles[0]
    assert p["full_name"] == "Sam Okafor"


def test_phones_always_e164_in_output():
    result = run([
        os.path.join(SAMPLES, "recruiter_export.csv"),
        os.path.join(SAMPLES, "ats_export.json"),
    ])
    for profile in result.profiles:
        for phone in profile["phones"]:
            assert phone.startswith("+"), f"phone not E.164: {phone}"
