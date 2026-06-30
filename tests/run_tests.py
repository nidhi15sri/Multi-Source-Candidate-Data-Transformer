#!/usr/bin/env python3
"""Tiny zero-dependency test runner. Run with: python3 tests/run_tests.py
(If pytest is available in your environment, `pytest tests/` also works since
the test functions follow standard pytest discovery/assert conventions.)"""
import sys
import traceback
import test_transformer as t

if __name__ == "__main__":
    tests = [
        (name, fn) for name, fn in vars(t).items()
        if name.startswith("test_") and callable(fn)
    ]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
