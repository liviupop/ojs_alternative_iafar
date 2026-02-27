#!/usr/bin/env python3
"""Extract Markdown twins from article PDFs using Microsoft MarkItDown."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from markitdown import MarkItDown

LOGGER = logging.getLogger("extract_article_markdown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate .md files from article PDFs using markitdown."
    )
    parser.add_argument(
        "--root",
        default="ingest",
        help="Root folder to scan for article PDFs (default: ingest).",
    )
    parser.add_argument(
        "--glob",
        default="**/articles/*.pdf",
        help="Glob pattern relative to root (default: **/articles/*.pdf).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .md files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N PDFs (0 = all).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def clean_markdown(text: str) -> str:
    cleaned = text.replace("\ufeff", "").replace("\x00", "")
    cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip() + "\n"


def collect_pdfs(root: Path, glob_pattern: str, limit: int) -> list[Path]:
    pdfs = sorted(root.glob(glob_pattern))
    # Ignore backup folders and hidden artifacts.
    pdfs = [
        path
        for path in pdfs
        if "articles_backup_" not in str(path)
        and "/." not in str(path).replace("\\", "/")
    ]
    if limit and limit > 0:
        return pdfs[:limit]
    return pdfs


def convert_pdf(markitdown: MarkItDown, pdf_path: Path) -> str:
    result = markitdown.convert(pdf_path)
    text = result.markdown or result.text_content or ""
    return clean_markdown(text)


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    pdf_paths = collect_pdfs(root, args.glob, args.limit)
    if not pdf_paths:
        LOGGER.warning("No PDFs found for pattern %s under %s", args.glob, root)
        return

    markitdown = MarkItDown()

    total = len(pdf_paths)
    converted = 0
    skipped = 0
    failed = 0

    LOGGER.info("Found %s PDFs", total)

    for idx, pdf_path in enumerate(pdf_paths, start=1):
        md_path = pdf_path.with_suffix(".md")
        if md_path.exists() and not args.force:
            skipped += 1
            if idx % 50 == 0 or idx == total:
                LOGGER.info(
                    "Progress %s/%s | converted=%s skipped=%s failed=%s",
                    idx,
                    total,
                    converted,
                    skipped,
                    failed,
                )
            continue

        try:
            markdown = convert_pdf(markitdown, pdf_path)
            if not markdown.strip():
                raise ValueError("Empty markdown output")
            md_path.write_text(markdown, encoding="utf-8")
            converted += 1
        except Exception as exc:
            failed += 1
            LOGGER.error("Failed converting %s: %s", pdf_path, exc)

        if idx % 25 == 0 or idx == total:
            LOGGER.info(
                "Progress %s/%s | converted=%s skipped=%s failed=%s",
                idx,
                total,
                converted,
                skipped,
                failed,
            )

    LOGGER.info(
        "Done | total=%s converted=%s skipped=%s failed=%s",
        total,
        converted,
        skipped,
        failed,
    )


if __name__ == "__main__":
    main()
