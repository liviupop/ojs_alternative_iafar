# PDF Ingest Pipeline v2 — Design

## Problem
Current pipeline uses Ghostscript txtwrite for text extraction, which loses ligatures (fi, fl, ff) producing corrupted metadata. Evidence: "inuential gure", "oers", "eldwork" in article_ranges.json.

## Solution
Replace GS txtwrite with PyMuPDF (fitz). Keep GS only for OCR image rendering.

## Key Changes
1. PyMuPDF replaces GS txtwrite — resolves ligatures, 10x faster
2. OCR: ron+eng+deu languages, 300 DPI
3. Ligature repair dictionary for edge cases
4. langdetect library for language detection
5. argparse CLI + env vars, no hardcoded paths
6. Python logging with per-article quality reports
7. pytest suite for parser, metadata, cleanup
8. Confidence calculated from extraction quality
9. Modular architecture (8 modules)
