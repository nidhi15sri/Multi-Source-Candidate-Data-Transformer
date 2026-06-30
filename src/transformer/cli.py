#!/usr/bin/env python3
"""
CLI for the Multi-Source Candidate Data Transformer.

Usage:
    python -m transformer.cli --inputs file1.csv file2.json resume.pdf notes.txt \
        [--config config.json] [--out output.json] [--pretty]

Prints the default-schema profiles as JSON to stdout (or --out file).
If --config is given, also emits the custom-projected output (to
<out>.custom.json or stdout if no --out).
Warnings/errors go to stderr so stdout stays clean JSON for piping.
"""
import argparse
import json
import sys

from .pipeline import run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--inputs", nargs="+", required=True,
                         help="Paths to source files (csv, json, pdf, docx, txt)")
    parser.add_argument("--config", help="Path to a runtime output-config JSON file")
    parser.add_argument("--out", help="Write default-schema output JSON to this path (default: stdout)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(argv)

    config = None
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)

    result = run(args.inputs, config=config)

    for w in result.warnings:
        print(f"[warning] {w}", file=sys.stderr)
    for e in result.errors:
        print(f"[error] {e}", file=sys.stderr)

    indent = 2 if args.pretty else None
    default_json = json.dumps(result.profiles, indent=indent)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(default_json)
        print(f"Wrote default-schema output: {args.out}", file=sys.stderr)
    else:
        print(default_json)

    if config:
        custom_json = json.dumps(result.custom_outputs, indent=indent)
        if args.out:
            custom_path = args.out.rsplit(".", 1)[0] + ".custom.json"
            with open(custom_path, "w", encoding="utf-8") as f:
                f.write(custom_json)
            print(f"Wrote custom-config output: {custom_path}", file=sys.stderr)
        else:
            print("--- custom config output ---")
            print(custom_json)

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
