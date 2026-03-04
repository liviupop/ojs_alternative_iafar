#!/usr/bin/env python3
"""Build ingest metadata for AAF first series (1932-1945, BCU scans).

This script is isolated from the modern pipeline so we do not affect
already-stable ingest logic for newer series.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ingest.series1 import process_issue, write_csv, write_json

LOGGER = logging.getLogger("ingest.series1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest AAF first series (BCU PDF files).")
    parser.add_argument(
        "--source-root",
        default="/Users/liviupop/Downloads",
        help="Folder containing BCUCLUJ_FP_490809_*.pdf files.",
    )
    parser.add_argument(
        "--glob",
        default="BCUCLUJ_FP_490809_*.pdf",
        help="Glob pattern for source PDFs.",
    )
    parser.add_argument(
        "--output-root",
        default="ingest/series1",
        help="Output root for generated metadata and copied sources.",
    )
    parser.add_argument(
        "--no-copy-source",
        action="store_true",
        help="Do not copy source issue PDF into output folders.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--unlock-series1",
        action="store_true",
        help="Allow regenerating Series 1 metadata (locked by default).",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def write_manifest_js(path: Path, issues: list[dict], articles: list[dict]) -> None:
    payload = {
        "issues": issues,
        "articles": articles,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.__INGEST_SERIES1 = {json.dumps(payload, ensure_ascii=False)};\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    if not args.unlock_series1:
        raise SystemExit(
            "Series 1 metadata is locked. "
            "Rerun only if you explicitly want overwrite: --unlock-series1"
        )

    source_root = Path(args.source_root).expanduser().resolve()
    out_root = Path(args.output_root).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(source_root.glob(args.glob))
    if not pdfs:
        raise SystemExit(f"No files matched: {source_root / args.glob}")

    all_issues: list[dict] = []
    all_rows: list[dict] = []
    for pdf_path in pdfs:
        issue_meta, rows = process_issue(pdf_path, out_root=out_root, copy_source_pdf=not args.no_copy_source)
        all_issues.append(issue_meta)
        all_rows.extend(rows)

    all_issues.sort(key=lambda issue: (issue.get("year", ""), issue.get("number", "")))

    write_json(out_root / "series1_issues.json", all_issues)
    write_json(out_root / "series1_articles.json", all_rows)
    write_manifest_js(out_root / "series1_manifest.js", all_issues, all_rows)
    write_csv(
        out_root / "series1_articles.csv",
        all_rows,
        fieldnames=[
            "series",
            "issue_slug",
            "year",
            "volume",
            "issue_number",
            "toc_index",
            "section",
            "author",
            "title",
            "pages_start_label",
            "pages_start",
            "pages_end",
            "abstract_fr",
            "keywords_fr",
            "keywords_ro",
            "summary_matched",
            "summary_pages_start",
            "summary_pages_end",
            "source_pdf",
            "toc_page_pdf",
            "summary_start_page_pdf",
            "article_pdf_path",
            "split_pages_start_pdf",
            "split_pages_end_pdf",
            "split_source_start_pdf",
            "split_source_end_pdf",
            "split_title_ok",
        ],
    )

    LOGGER.info(
        "Series1 done: issues=%s articles=%s output=%s",
        len(all_issues),
        len(all_rows),
        out_root,
    )


if __name__ == "__main__":
    main()
