"""Local JSON file orchestration and atomic report writing."""

import json
import logging
import os
import tempfile
from pathlib import Path

from .pipeline import process_articles


logger = logging.getLogger(__name__)


def write_report(path: Path, report: dict) -> None:
    """Replace output atomically; clean up temporary files on failure."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_pipeline(input_path: str | Path, output_path: str | Path) -> dict:
    """Load local articles, process them, write a report, and return it."""
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve() or (
        output_path.exists() and input_path.samefile(output_path)
    ):
        raise ValueError("input and output must be different files")
    logger.info("Reading JSON from %s", input_path)
    with input_path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    report = process_articles(data)
    logger.info("Writing report to %s", output_path)
    write_report(output_path, report)
    logger.info("Report saved successfully")
    return report
