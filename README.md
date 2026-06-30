# Multi-Source Candidate Data Transformer

## Quick start

```bash
pip install -r requirements.txt   # pdfplumber, python-docx (stdlib covers the rest)

# Default schema output
PYTHONPATH=src python3 -m transformer.cli \
  --inputs sample_inputs/recruiter_export.csv sample_inputs/ats_export.json \
           sample_inputs/priya_shah_resume.pdf sample_inputs/sam_okafor_resume.docx \
           sample_inputs/recruiter_notes_arjun.txt sample_inputs/recruiter_notes_maria.txt \
  --pretty --out sample_outputs/default_output.json

# With a custom output config (the "required twist")
PYTHONPATH=src python3 -m transformer.cli \
  --inputs <same files as above> \
  --config sample_inputs/custom_config_example.json \
  --pretty --out sample_outputs/default_output.json
# -> also writes sample_outputs/default_output.custom.json
```

Warnings/errors (missing files, garbage sources, validation issues) print to
stderr; stdout/`--out` stays clean JSON.

## Running tests

```bash
cd tests && PYTHONPATH=../src python3 run_tests.py
# or, if pytest is installed:
PYTHONPATH=src python3 -m pytest tests/ -v
```

10/10 tests currently pass, covering normalization, cross-source merging,
provenance, missing/garbage source handling, and PDF/DOCX resume extraction.

## Project layout

```
src/transformer/
  detect.py        # "ingest" stage — routes a file path to the right parser
  models.py         # internal CandidateRecord model (value+provenance)
  normalize.py      # "standardize" stage — phone/date/skill/email/country normalization
  extractors/        # "parse" stage — one module per source type
    csv_extractor.py
    json_extractor.py
    resume_extractor.py
    notes_extractor.py
  merge.py          # "reconcile" stage: match (group_records) + resolve (merge_group), plus "score" (confidence)
  project.py        # "shape" stage — default-schema builder + runtime config projection
  validate.py       # "verify" stage — schema/required-field validation
  pipeline.py        # orchestrates ingest→parse→standardize→reconcile→score→shape→verify
  cli.py            # command-line entry point
tests/
  test_transformer.py
  run_tests.py      # zero-dependency runner
sample_inputs/      # sample CSV/JSON/PDF/DOCX/TXT + a garbage JSON for the edge-case demo
sample_outputs/     # example run output
design_doc/         # the one-page technical design PDF + its build script
```

## Custom output config format

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


