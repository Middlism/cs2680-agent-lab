"""CLI: python -m news_pipeline INPUT OUTPUT [--verbose]."""

import argparse
import logging
import sys
from pathlib import Path

from .io import run_pipeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Process a local financial news JSON file.")
    parser.add_argument("input", type=Path, help="UTF-8 JSON array of articles")
    parser.add_argument("output", type=Path, help="JSON report path (parent directory must exist)")
    parser.add_argument("--verbose", action="store_true", help="Trace processing stages to stderr")
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    try:
        report = run_pipeline(args.input, args.output)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(f"Wrote {summary['output_count']} articles to {args.output} "
          f"({summary['duplicates_removed']} duplicates removed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
