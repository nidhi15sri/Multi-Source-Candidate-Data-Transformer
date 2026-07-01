# Multi-Source Candidate Data Transformer

## Sources implemented

**Structured (pick at least one — both implemented):**
- Recruiter CSV export (`csv_extractor.py`) — name, email, phone, company, title
- ATS JSON blob (`json_extractor.py`) — semi-structured, with its own field names that do NOT match ours

**Unstructured (pick at least one — both implemented):**
- Resume files — PDF and DOCX (`resume_extractor.py`)
- Recruiter notes `.txt` (`notes_extractor.py`) — free text

---

## Installation

```
pip install -r requirements.txt
```

Only two non-stdlib dependencies: `pdfplumber` (PDF text extraction) and `python-docx` (DOCX extraction).

---

## Running (Windows PowerShell)

**Step 1 — set PYTHONPATH once per terminal session:**
```
$env:PYTHONPATH = "src"
```

**Step 2 — default schema output:**
```
python -m transformer.cli --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json sample_inputs/priya_shah_resume.pdf sample_inputs/sam_okafor_resume.docx sample_inputs/recruiter_notes_arjun.txt sample_inputs/recruiter_notes_maria.txt --pretty
```

**Step 3 — with a custom output config (the "required twist"):**
```
python -m transformer.cli --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json sample_inputs/priya_shah_resume.pdf sample_inputs/sam_okafor_resume.docx sample_inputs/recruiter_notes_arjun.txt sample_inputs/recruiter_notes_maria.txt --config sample_inputs/custom_config_example.json --pretty
```

This produces two outputs: the full default-schema JSON, and (after `--- custom config output ---`) a smaller reshaped JSON driven by the config — same underlying merged data, different shape, zero code changes.

**Step 4 — robustness demo (garbage + missing source):**
```
python -m transformer.cli --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json sample_inputs/garbage_ats.json sample_inputs/does_not_exist.csv --pretty
```

Warnings go to stderr; the pipeline continues with whatever good sources remain.

**Save output to a file instead of printing:**
```
python -m transformer.cli --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json --pretty --out sample_outputs/default_output.json
```

---

## Running (Mac / Linux)

```bash
PYTHONPATH=src python3 -m transformer.cli \
  --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json \
           sample_inputs/priya_shah_resume.pdf sample_inputs/sam_okafor_resume.docx \
           sample_inputs/recruiter_notes_arjun.txt sample_inputs/recruiter_notes_maria.txt \
  --pretty
```

---

## Running tests

```
cd tests
python run_tests.py
cd ..
```

10/10 tests pass, covering: phone/date/skill/email normalization, cross-source merging,
provenance tracking, missing/garbage source handling, and PDF/DOCX resume extraction.

If pytest is available in your environment, the standard discovery also works:
```
python -m pytest tests/ -v
```

---

## Pipeline stages

```
ingest → parse → standardize → reconcile (match + resolve) → score → shape → verify
```

| Stage | File | What it does |
|---|---|---|
| ingest | `detect.py` | Routes each file to the right parser by extension + content sniff |
| parse | `extractors/` | One module per source type; every value gets provenance metadata |
| standardize | `normalize.py` | Phones → E.164, dates → YYYY-MM, skills → canonical names, countries → ISO-3166 |
| reconcile | `merge.py` | match: union-find on shared email/phone/name; resolve: pick winner per field |
| score | `merge.py` | Corroboration boost (+0.12 per agreeing source, cap 0.97); overall_confidence = mean of populated fields |
| shape | `project.py` | Build default schema; optionally re-project through runtime config |
| verify | `validate.py` | Schema checks; collect warnings, never raise on bad source |

---

## Project layout

```
src/transformer/
  detect.py           # ingest stage
  models.py           # internal CandidateRecord model (value + provenance)
  normalize.py        # standardize stage
  extractors/
    csv_extractor.py
    json_extractor.py
    resume_extractor.py
    notes_extractor.py
  merge.py            # reconcile + score stages
  project.py          # shape stage
  validate.py         # verify stage
  pipeline.py         # orchestrator
  cli.py              # command-line entry point
tests/
  test_transformer.py
  run_tests.py        # zero-dependency runner (no pytest needed)
sample_inputs/        # CSV, JSON, PDF, DOCX, TXT + garbage_ats.json for edge-case demo
sample_outputs/       # example run output (committed so reviewer can see results without running)
design_doc/           # one-page technical design PDF
```

---

## Custom output config format (the "required twist")

The `--config` flag accepts a JSON file that reshapes the output without touching
the pipeline. The same canonical merged record, projected differently:

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E.164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

Each field supports:
- `path` — output key name
- `from` — dotted/bracket path into the default profile (e.g. `emails[0]`, `location.country`)
- `normalize` — `E.164` for phones, `canonical` for skills
- `required` — whether to enforce presence
- `include_confidence` — attach a `_confidence` block to the output
- `on_missing` — `null` (output null), `omit` (drop the field), or `error` (fail the run)

---

## Known limitations (deliberately scoped out)

- **Phone normalization is heuristic** — no `phonenumbers` library (not installable offline). A bare 10-digit number with no country code is assumed US/Canada. This causes a known mis-normalisation for Arjun Mehta's Indian number in the sample data — documented honestly rather than hidden.
- **Experience/education dedup is exact-match only** — "Sr. Backend Engineer" and "Senior Backend Engineer" are treated as two different roles. Fuzzy title matching is a scope cut.
- **No GitHub/LinkedIn live-fetch** — requires network calls unavailable in the build environment. The extractor interface is designed so adding them is one new module following the same pattern.
