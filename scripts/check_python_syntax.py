#!/usr/bin/env python3
"""Check trusted repository Python sources without writing bytecode caches."""
import argparse
from pathlib import Path
import tokenize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    if not all(root.is_dir() for root in args.roots):
        parser.error("syntax roots must be existing directories")
    files = sorted({path for root in args.roots for path in root.rglob("*.py")})
    for path in files:
        with tokenize.open(path) as source:
            compile(source.read(), str(path), "exec", dont_inherit=True)
    print(f"Python syntax passed: {len(files)} files; no bytecode written.")


if __name__ == "__main__":
    main()
