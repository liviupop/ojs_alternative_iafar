#!/usr/bin/env python3
"""
Build script for Series 2 article PDF splitting.

Reads existing toc_entries.json per issue (parsed from the markdown TOC),
sorts entries by page_start, recalculates page_end = next_entry.page_start - 1,
and splits the source PDFs into individual article PDFs.

Usage:
    .venv/bin/python scripts/build_ingest_series2.py
    .venv/bin/python scripts/build_ingest_series2.py --issue aaf-seria2-1980-vol-i
    .venv/bin/python scripts/build_ingest_series2.py --manifest-only
"""

import json, os, re, sys, unicodedata, logging, shutil
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("build_series2")

# ── Issue definitions ─────────────────────────────────────────────
ISSUES = [
    {
        "pdf": "Anuarul_de_folclor_I.pdf",
        "slug": "aaf-seria2-1980-vol-i",
        "year": "1980",
        "volume": "I",
        "number": "1",
        "title": "Anuarul de folclor I",
    },
    {
        "pdf": "Anuarul_de_folclor_II.pdf",
        "slug": "aaf-seria2-1984-vol-ii",
        "year": "1984",
        "volume": "II",
        "number": "2",
        "title": "Anuarul de folclor II",
    },
    {
        "pdf": "Anuarul_de_folclor_III-IV.pdf",
        "slug": "aaf-seria2-1985-1986-vol-iii-iv",
        "year": "1985-1986",
        "volume": "III-IV",
        "number": "3-4",
        "title": "Anuarul de folclor III-IV",
    },
    {
        "pdf": "Anuarul_de_folclor_V-VII.pdf",
        "slug": "aaf-seria2-1987-1989-vol-v-vii",
        "year": "1987-1989",
        "volume": "V-VII",
        "number": "5-7",
        "title": "Anuarul de folclor V-VII",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_VIII-XI.pdf",
        "slug": "aaf-seria2-1990-1993-vol-viii-xi",
        "year": "1990-1993",
        "volume": "VIII-XI",
        "number": "8-11",
        "title": "Anuarul Arhivei de folclor VIII-XI",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XII-XIV.pdf",
        "slug": "aaf-seria2-1994-1995-vol-xii-xiv",
        "year": "1994-1995",
        "volume": "XII-XIV",
        "number": "12-14",
        "title": "Anuarul Arhivei de folclor XII-XIV",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XV-XVII.pdf",
        "slug": "aaf-seria2-1996-1998-vol-xv-xvii",
        "year": "1996-1998",
        "volume": "XV-XVII",
        "number": "15-17",
        "title": "Anuarul Arhivei de folclor XV-XVII",
    },
]

# Entries to exclude (back-matter, not articles)
EXCLUDE_TITLES = {
    "COLABORATORI",
    "ABREVIERI",
    "ABREVIERE",
    "ABREVIERI ",
    "LISTA COLABORATORILOR",
}


def slugify(text: str, max_len: int = 120) -> str:
    """Create a URL-safe slug from text."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:max_len]


def should_exclude(entry: dict) -> bool:
    """Check if an entry is back-matter that should be excluded."""
    title = (entry.get("title") or "").strip()
    title_upper = title.upper().strip()
    if title_upper in EXCLUDE_TITLES:
        return True
    if title_upper.startswith("COLABORATOR"):
        return True
    if title_upper.startswith("ABREVIE"):
        return True
    return False


def process_issue(issue_def: dict, series2_dir: Path, issues_dir: Path) -> dict:
    """Process a single Series 2 issue: read TOC, sort, split PDF."""
    slug = issue_def["slug"]
    pdf_path = series2_dir / issue_def["pdf"]
    issue_dir = issues_dir / slug
    articles_dir = issue_dir / "articles"
    metadata_dir = issue_dir / "metadata"
    toc_path = metadata_dir / "toc_entries.json"

    if not pdf_path.exists():
        log.error(f"PDF not found: {pdf_path}")
        return {"slug": slug, "error": f"PDF not found: {pdf_path}"}

    if not toc_path.exists():
        log.error(f"TOC not found: {toc_path}")
        return {"slug": slug, "error": f"TOC not found: {toc_path}"}

    # Read existing TOC entries
    with open(toc_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    log.info(f"\n{'='*60}")
    log.info(f"Processing: {issue_def['title']} ({issue_def['year']})")
    log.info(f"PDF: {pdf_path.name} | TOC entries: {len(entries)}")
    log.info(f"{'='*60}")

    # Filter out back-matter entries
    filtered = [e for e in entries if not should_exclude(e)]
    excluded_count = len(entries) - len(filtered)
    if excluded_count:
        log.info(f"Excluded {excluded_count} back-matter entries (COLABORATORI/ABREVIERI)")

    # Filter out entries without page_start
    valid = [e for e in filtered if e.get("page_start") and isinstance(e["page_start"], int)]
    skipped = len(filtered) - len(valid)
    if skipped:
        log.warning(f"Skipped {skipped} entries without valid page_start")

    # Sort by page_start (critical for RECENZII sections which are alphabetical in TOC)
    valid.sort(key=lambda e: e["page_start"])

    # Open PDF
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    log.info(f"Total PDF pages: {total_pages}")

    # Recalculate page_end based on sorted order
    # Rule: article ends on the page before the next article starts
    # Guard: if two entries share the same page_start, ensure page_end >= page_start
    for i, entry in enumerate(valid):
        if i + 1 < len(valid):
            next_start = valid[i + 1]["page_start"]
            entry["page_end"] = max(entry["page_start"], next_start - 1)
        else:
            # Last article: goes to end of content (estimate: total_pages - 1)
            entry["page_end"] = total_pages - 1

    # Clean old articles directory
    if articles_dir.exists():
        old_pdfs = list(articles_dir.glob("*.pdf"))
        if old_pdfs:
            log.info(f"Removing {len(old_pdfs)} old article PDFs")
            for f in old_pdfs:
                f.unlink()
    articles_dir.mkdir(parents=True, exist_ok=True)

    # Split PDF into individual articles
    # Offset = 0: printed page N = PDF index N (user confirmed)
    split_results = []
    for i, entry in enumerate(valid):
        start_pdf = entry["page_start"]
        end_pdf = entry["page_end"]

        # Clamp to valid PDF range
        start_pdf = max(0, min(start_pdf, total_pages - 1))
        end_pdf = max(start_pdf, min(end_pdf, total_pages - 1))

        # Include one extra page before and after the TOC range so that
        # text bleeding across page boundaries is captured during extraction.
        # Metadata page_start / page_end stay exact (from TOC).
        split_start = max(0, start_pdf - 1)
        split_end = min(end_pdf + 1, total_pages - 1)

        idx_str = str(i + 1).zfill(3)
        title_slug = slugify(entry.get("title", "untitled"))
        filename = f"{idx_str}-{title_slug}.pdf"

        out_doc = fitz.open()
        out_doc.insert_pdf(doc, from_page=split_start, to_page=split_end)
        out_path = articles_dir / filename
        out_doc.save(str(out_path))
        out_doc.close()

        num_pages = split_end - split_start + 1
        log.info(
            f"  [{idx_str}] pp.{entry['page_start']}-{entry['page_end']} "
            f"(pdf {split_start}-{split_end}, {num_pages}p) | {filename[:80]}"
        )

        split_results.append({
            "index": i + 1,
            "section": entry.get("section", ""),
            "author": entry.get("author", ""),
            "title": entry.get("title", ""),
            "page_start_label": str(entry["page_start"]),
            "page_start": entry["page_start"],
            "page_end": entry["page_end"],
            "article_pdf": filename,
            "pdf_page_start": start_pdf,
            "pdf_page_end": end_pdf,
        })

    doc.close()

    # Write updated toc_entries.json (sorted, with corrected page_end)
    toc_out = []
    for r in split_results:
        toc_out.append({
            "index": r["index"],
            "section": r["section"],
            "author": r["author"],
            "title": r["title"],
            "page_start_label": r["page_start_label"],
            "page_start": r["page_start"],
            "page_end": r["page_end"],
        })

    with open(toc_path, "w", encoding="utf-8") as f:
        json.dump(toc_out, f, ensure_ascii=False, indent=2)
    log.info(f"Updated {toc_path} ({len(toc_out)} entries)")

    return {
        "slug": slug,
        "entries": len(split_results),
        "articles_dir": str(articles_dir),
    }


def parse_first_year(value: str) -> int:
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group(0)) if match else 0


def clean_display_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("|", " ").replace(" _", " ").replace("_ ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\.\s*\.\s*\.\s*", " ", text)
    text = re.sub(r"^[\-\.,:;]+", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_manifest(issues_dir: Path, manifest_path: Path):
    """Build series2 manifest from split article PDFs + TOC metadata."""
    issues = []
    articles = []

    for issue_dir in sorted(issues_dir.iterdir()):
        if not issue_dir.is_dir():
            continue
        issue_json = issue_dir / "metadata" / "issue.json"
        toc_json = issue_dir / "metadata" / "toc_entries.json"
        articles_dir = issue_dir / "articles"

        if not toc_json.exists():
            continue

        # Read issue metadata (may not exist for all)
        issue_meta = {}
        if issue_json.exists():
            with open(issue_json, "r", encoding="utf-8") as f:
                issue_meta = json.load(f)

        with open(toc_json, "r", encoding="utf-8") as f:
            toc_entries = json.load(f)

        # Count actual PDF files
        pdf_count = 0
        if articles_dir.exists():
            pdf_count = len(list(articles_dir.glob("*.pdf")))

        slug = issue_meta.get("slug", issue_dir.name)
        source_pdf_name = str(issue_meta.get("source_pdf_name", "")).strip()

        issue_item = {
            "slug": slug,
            "series": "seria-2",
            "series_label": "Seria II (1980-1998)",
            "year": issue_meta.get("year", ""),
            "volume": issue_meta.get("volume", ""),
            "number": issue_meta.get("number", ""),
            "title": issue_meta.get("title", ""),
            "issue_pdf_path": f"ingest/series2/{source_pdf_name}" if source_pdf_name else "",
            "article_count": pdf_count,
        }
        issues.append(issue_item)

        for entry in toc_entries:
            idx = entry.get("index", 0)
            title = clean_display_text(entry.get("title", ""))
            author = clean_display_text(entry.get("author", ""))
            section = clean_display_text(entry.get("section", ""))
            page_start = entry.get("page_start")
            page_end = entry.get("page_end")

            # Find matching article PDF
            idx_str = str(idx).zfill(3)
            pdf_files = list(articles_dir.glob(f"{idx_str}-*.pdf")) if articles_dir.exists() else []
            article_pdf = ""
            if pdf_files:
                article_pdf = f"ingest/series2/issues/{slug}/articles/{pdf_files[0].name}"

            articles.append({
                "issue_slug": slug,
                "index": idx,
                "section": section,
                "author": author,
                "title": title,
                "page_start": page_start,
                "page_end": page_end,
                "article_pdf_path": article_pdf,
            })

    # Sort issues by year (newest first)
    issues.sort(
        key=lambda i: (parse_first_year(i.get("year", "")), i.get("slug", "")),
        reverse=True,
    )
    issue_order = {iss["slug"]: idx for idx, iss in enumerate(issues)}
    articles.sort(key=lambda a: (issue_order.get(a.get("issue_slug", ""), 10000), a.get("index", 0)))

    import datetime
    manifest = {
        "issues": issues,
        "articles": articles,
        "generated_at": datetime.datetime.now().isoformat(),
    }

    js_content = f"window.__INGEST_SERIES2 = {json.dumps(manifest, ensure_ascii=False, indent=2)};\n"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    log.info(f"\nManifest: {len(issues)} issues, {len(articles)} articles → {manifest_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build Series 2 article PDFs from TOC")
    parser.add_argument("--series2-dir", default="ingest/series2",
                        help="Directory containing Series 2 source PDFs")
    parser.add_argument("--issues-dir", default="ingest/series2/issues",
                        help="Directory containing issue folders with toc_entries.json")
    parser.add_argument("--issue", default=None,
                        help="Process only this issue slug")
    parser.add_argument("--manifest-only", action="store_true",
                        help="Only regenerate the manifest from existing data")
    parser.add_argument("--manifest-path", default="ingest/series2/series2_manifest.js",
                        help="Output path for the JS manifest")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    series2_dir = Path(args.series2_dir)
    issues_dir = Path(args.issues_dir)
    manifest_path = Path(args.manifest_path)

    if args.manifest_only:
        build_manifest(issues_dir, manifest_path)
        return

    # Determine which issues to process
    if args.issue:
        issues_to_process = [i for i in ISSUES if i["slug"] == args.issue]
        if not issues_to_process:
            log.error(f"Unknown issue slug: {args.issue}")
            log.info("Available: " + ", ".join(i["slug"] for i in ISSUES))
            sys.exit(1)
    else:
        issues_to_process = ISSUES

    results = []
    for issue_def in issues_to_process:
        result = process_issue(issue_def, series2_dir, issues_dir)
        results.append(result)

    # Build manifest
    build_manifest(issues_dir, manifest_path)

    # Summary
    log.info(f"\n{'='*60}")
    log.info("SUMMARY")
    log.info(f"{'='*60}")
    total = 0
    for r in results:
        if "error" in r:
            log.error(f"  FAILED {r['slug']}: {r['error']}")
        else:
            log.info(f"  {r['slug']}: {r['entries']} articles")
            total += r["entries"]
    log.info(f"  TOTAL: {total} articles")


if __name__ == "__main__":
    main()
