#!/usr/bin/env python3
"""Run behavioral development regressions in one process with shared fixtures."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import unittest

GROUPS = {
    "documents": ("test_extraction_sync_fidelity", "test_requirement_accuracy", "test_requirement_revisions",
                  "test_source_references", "test_table_boundaries"),
    "reports": ("test_report_lineage", "test_report_offline_workflow", "test_report_values",
                "test_formula_conversion", "test_multisource_conversion"),
}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=root)
    parser.add_argument("--group", choices=("all", *GROUPS), default="all")
    parser.add_argument("--list", action="store_true", help="List test IDs without executing them.")
    args = parser.parse_args()
    sys.path.insert(0, str(root / "scripts/tests"))
    import pipeline_test_support
    pipeline_test_support.SOURCE_ROOT = args.source_root.resolve()
    modules = [name for group, names in GROUPS.items() if args.group in {"all", group} for name in names]
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)) for name in modules)
    if args.list:
        def ids(value):
            if isinstance(value, unittest.TestSuite):
                return [name for child in value for name in ids(child)]
            return [value.id()]
        print(json.dumps(ids(suite), indent=2))
        return 0
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
