#!/usr/bin/env python3
"""Extract markdown text from all Series 1 article PDFs using OCR.

Usage:
    .venv/bin/python scripts/extract_series1_md.py [--force]

For each PDF in ingest/series1/issues/*/articles/*.pdf, produces a .md file
alongside it. Skips existing .md files unless --force is given.

Series 1 PDFs are image-only scans (1932-1945), so we use:
  1. PyMuPDF text extraction first (fast)
  2. Tesseract OCR fallback if text is weak (300 DPI, ron+eng+deu+fra)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure scripts/ is on the path so we can import the ingest package.
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from ingest.pdf_extract import (
    extract_text_range,
    extraction_is_weak,
    ocr_extract_text_range,
    page_count,
)
from ingest.text_cleanup import normalize_full_text

ROOT = SCRIPTS_DIR.parent
SERIES1_DIR = ROOT / "ingest" / "series1" / "issues"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
LOG = logging.getLogger("extract_s1")


def extract_pdf_to_md(pdf_path: Path, force: bool = False) -> bool:
    """Extract text from a single PDF and write a .md file.

    Returns True if the .md file was written (new or updated).
    """
    md_path = pdf_path.with_suffix(".md")
    if md_path.exists() and not force:
        LOG.debug("Skip (exists): %s", md_path.name)
        return False

    stem = pdf_path.stem
    total = page_count(pdf_path)
    LOG.info("  %s (%d pages)", stem, total)

    # Step 1: try PyMuPDF text extraction (fast, works if PDF has text layer).
    text = extract_text_range(pdf_path, 1, total)
    source = "fitz"

    # Step 2: if text is weak (image-only PDF), fall back to OCR.
    if extraction_is_weak(text, min_chars=200, min_words=40):
        LOG.info("    fitz weak (%d chars) → OCR", len(text.strip()))
        ocr_text = ocr_extract_text_range(pdf_path, 1, total, temp_stem=stem)
        if ocr_text.strip():
            text = ocr_text
            source = "ocr"
        else:
            LOG.warning("    OCR also returned empty for %s", stem)

    # Normalize and write.
    text = normalize_full_text(text)
    if not text.strip():
        LOG.warning("    No text extracted for %s", stem)
        md_path.write_text(f"<!-- No text extracted from {pdf_path.name} -->\n", encoding="utf-8")
        return True

    header = f"<!-- Extracted from {pdf_path.name} via {source} -->\n\n"
    md_path.write_text(header + text + "\n", encoding="utf-8")
    LOG.info("    ✓ %s → %d chars [%s]", md_path.name, len(text), source)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract .md from Series 1 PDFs")
    parser.add_argument("--force", action="store_true", help="Overwrite existing .md files")
    args = parser.parse_args()

    # Collect all article PDFs across all Series 1 issues.
    pdfs = sorted(SERIES1_DIR.glob("*/articles/*.pdf"))
    LOG.info("Found %d article PDFs in Series 1", len(pdfs))

    written = 0
    skipped = 0
    errors = 0
    t0 = time.time()

    for pdf in pdfs:
        issue_slug = pdf.parent.parent.name
        if written == 0 or pdf == pdfs[0]:
            LOG.info("── %s ──", issue_slug)
        elif pdf.parent.parent.name != pdfs[pdfs.index(pdf) - 1].parent.parent.name:
            LOG.info("── %s ──", issue_slug)

        try:
            if extract_pdf_to_md(pdf, force=args.force):
                written += 1
            else:
                skipped += 1
        except Exception:
            LOG.exception("Error processing %s", pdf)
            errors += 1

    elapsed = time.time() - t0
    LOG.info(
        "Done: %d written, %d skipped, %d errors in %.1fs",
        written, skipped, errors, elapsed,
    )


if __name__ == "__main__":
    main()
