#!/usr/bin/env python3
"""Build ingest library for AAF issues.

Priority order implemented:
P0: PyMuPDF extraction/splitting, no Ghostscript txtwrite/pagecount hacks.
P1: OCR fallback with multilingual Tesseract at 300 DPI.
P2: Robust TOC + metadata parsing.
P3: Data quality scoring/confidence derived from extraction quality.
P4: Modular orchestrator with argparse + logging + env-based config.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

from ingest.config import (
    DEFAULT_AFFILIATION,
    ISSUES_INPUT,
    KEYWORD_STOPWORDS,
    OUT_ROOT,
    PDFTOTEXT_BIN,
    ROOT,
    TMP_ROOT,
)
from ingest.manifest import build_global_manifest, build_issue_meta
from ingest.metadata import parse_frontmatter
from ingest.pdf_extract import (
    extract_text_best_effort,
    extract_markdown_with_markitdown,
    find_text_hits,
    page_count,
    score_text_quality,
)
from ingest.splitter import split_article_pdf
from ingest.text_cleanup import normalize_full_text, normalize_text, slugify
from ingest.toc_parser import parse_toc_entries

LOGGER = logging.getLogger("ingest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AAF ingest library from issue PDFs.")
    parser.add_argument(
        "--issue",
        action="append",
        default=[],
        help="Issue slug to process (repeatable). Default: all.",
    )
    parser.add_argument(
        "--source-root",
        default="",
        help="Override source PDF folder; filenames are resolved from configured issues.",
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


def resolve_issues(source_root_override: str, slugs: list[str]) -> list[dict]:
    issues = [{**issue} for issue in ISSUES_INPUT]

    if source_root_override:
        source_root = Path(source_root_override)
        for issue in issues:
            issue["src_pdf"] = source_root / Path(issue["src_pdf"]).name

    if slugs:
        wanted = set(slugs)
        issues = [issue for issue in issues if issue["slug"] in wanted]

    return issues


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_toc_text(local_pdf: Path, total_pages: int, out_txt: Path) -> str:
    """Extract TOC text; prefer pdftotext layout mode when available."""
    pages = min(80, total_pages)

    if PDFTOTEXT_BIN and Path(PDFTOTEXT_BIN).exists():
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            PDFTOTEXT_BIN,
            "-f",
            "1",
            "-l",
            str(pages),
            "-layout",
            "-enc",
            "UTF-8",
            str(local_pdf),
            str(out_txt),
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode == 0 and out_txt.exists():
            text = out_txt.read_text(errors="ignore")
            if text.strip():
                return text
        LOGGER.warning("pdftotext failed for %s, fallback to fitz: %s", local_pdf, proc.stderr.strip())

    text, _source = extract_text_best_effort(
        local_pdf,
        1,
        pages,
        temp_stem=f"{local_pdf.stem}-toc",
        min_chars=1200,
        min_words=200,
    )
    out_txt.write_text(text, encoding="utf-8")
    return text


def infer_page_offset(local_pdf: Path, first_entry: dict | None, total_pages: int) -> int:
    if not first_entry:
        return 0

    printed_start = int(first_entry.get("start_page", 1))
    needle = normalize_text(first_entry.get("title", ""))[:70]
    if not needle:
        return 0

    hits = find_text_hits(local_pdf, needle, max_pages=min(total_pages, printed_start + 120))
    candidates = [page for page in hits if page >= printed_start]
    if candidates:
        return candidates[0] - printed_start

    # Fallback: nearest hit even if before printed start.
    if hits:
        nearest = min(hits, key=lambda page: abs(page - printed_start))
        return nearest - printed_start

    return 0


def build_article_md(
    entry: dict,
    frontmatter: dict,
    issue_meta: dict,
    full_text: str,
    markdown_body: str,
) -> str:
    lines = [
        f"# {entry['title']}",
        "",
        f"- Autor(i): {frontmatter.get('authors', 'N/A')}",
        f"- Secțiune TOC: {entry.get('section', '') or 'N/A'}",
        f"- Pagini: p. {entry['start_page']}–{entry['end_page']}",
        f"- Afiliere: {frontmatter.get('affiliation', '') or 'N/A'}",
        f"- Email: {frontmatter.get('emails', '') or 'N/A'}",
        f"- DOI: {frontmatter.get('doi', '') or 'N/A'}",
        f"- Limbă: {frontmatter.get('language', 'ro')}",
        f"- Tip intrare: {'recenzie' if frontmatter.get('is_review') else 'articol'}",
        f"- Număr: Vol. {issue_meta.get('volume', '')} Nr. {issue_meta.get('number', '')} ({issue_meta.get('year', '')})",
        "",
        "## Abstract",
        frontmatter.get("abstract_en", "") or "_Nedetectat_",
        "",
        "## Keywords",
        frontmatter.get("keywords_en", "") or "_Nedetectate_",
        "",
        "## Text extras din PDF (Markdown)",
        markdown_body or "_Markdown indisponibil_",
        "",
        "## Text extras din PDF (fallback text)",
        full_text or "_Text indisponibil_",
        "",
    ]
    return "\n".join(lines)


def build_issue(issue_input: dict) -> tuple[dict, list[dict]]:
    issue_dir = OUT_ROOT / issue_input["slug"]
    src_dir = issue_dir / "source"
    meta_dir = issue_dir / "metadata"
    articles_dir = issue_dir / "articles"
    md_dir = issue_dir / "md"
    cover_dir = issue_dir / "cover"

    src_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    articles_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    # Ensure deterministic outputs on re-run: clear generated article/md files.
    for old_pdf in articles_dir.glob("*.pdf"):
        old_pdf.unlink(missing_ok=True)
    for old_md in md_dir.glob("*.md"):
        old_md.unlink(missing_ok=True)

    src_pdf = Path(issue_input["src_pdf"])
    if not src_pdf.exists():
        raise FileNotFoundError(f"Missing source PDF: {src_pdf}")

    local_pdf = src_dir / "issue.pdf"
    if not local_pdf.exists() or local_pdf.stat().st_size != src_pdf.stat().st_size:
        shutil.copy2(src_pdf, local_pdf)

    total_pages = page_count(local_pdf)

    toc_txt = meta_dir / "toc_raw.txt"
    toc_text = extract_toc_text(local_pdf, total_pages, toc_txt)
    entries = parse_toc_entries(toc_text)

    if not entries:
        raise RuntimeError(f"No TOC entries parsed for {issue_input['slug']}")

    offset = infer_page_offset(local_pdf, entries[0], total_pages)

    issue_meta = build_issue_meta(issue_input, total_pages)
    issue_meta["page_offset"] = offset

    processed: list[dict] = []

    for idx, entry in enumerate(entries, start=1):
        start_printed = int(entry["start_page"])
        next_start = entries[idx]["start_page"] if idx < len(entries) else (total_pages - offset + 1)
        end_printed = max(start_printed, int(next_start) - 1)

        start_pdf = max(1, start_printed + offset)
        end_pdf = min(total_pages, end_printed + offset)
        if end_pdf < start_pdf:
            LOGGER.warning(
                "Skip entry with invalid pages: %s (%s-%s)",
                entry.get("title", "?"),
                start_pdf,
                end_pdf,
            )
            continue

        title_slug = slugify(entry["title"])
        article_rel = f"ingest/issues/{issue_input['slug']}/articles/{idx:03d}-{title_slug}.pdf"
        article_abs = ROOT / article_rel

        split_article_pdf(local_pdf, article_abs, start_pdf, end_pdf)
        article_page_count = max(1, end_pdf - start_pdf + 1)

        front_last = min(2, article_page_count)
        first_page_text, first_page_source = extract_text_best_effort(
            article_abs,
            1,
            1,
            temp_stem=f"{issue_input['slug']}-{idx:03d}-first-page",
            min_chars=100,
            min_words=15,
        )

        front_text, front_source = extract_text_best_effort(
            article_abs,
            1,
            front_last,
            temp_stem=f"{issue_input['slug']}-{idx:03d}-front",
            min_chars=150,
            min_words=20,
        )

        full_text_raw, full_source = extract_text_best_effort(
            article_abs,
            1,
            article_page_count,
            temp_stem=f"{issue_input['slug']}-{idx:03d}-full",
            min_chars=max(320, article_page_count * 90),
            min_words=max(55, article_page_count * 22),
        )
        full_text = normalize_full_text(full_text_raw)
        markdown_body = extract_markdown_with_markitdown(article_abs)
        if not markdown_body:
            markdown_body = full_text

        front_quality = score_text_quality(front_text)
        full_quality = score_text_quality(full_text)
        quality = round((front_quality * 0.6) + (full_quality * 0.4), 3)

        entry_with_pages = {
            **entry,
            "start_page": start_printed,
            "end_page": end_printed,
        }

        parsed = parse_frontmatter(
            front_text=front_text,
            first_page_text=first_page_text,
            full_text=full_text,
            entry=entry_with_pages,
            keyword_stopwords=KEYWORD_STOPWORDS,
            text_quality=quality,
        )

        md_rel = f"ingest/issues/{issue_input['slug']}/md/{idx:03d}-{title_slug}.md"
        md_abs = ROOT / md_rel
        md_abs.parent.mkdir(parents=True, exist_ok=True)
        md_abs.write_text(
            build_article_md(entry_with_pages, parsed, issue_meta, full_text, markdown_body),
            encoding="utf-8",
        )

        processed.append(
            {
                "index": idx,
                "section": entry.get("section", ""),
                "title": entry["title"],
                "author": entry.get("author", ""),
                "authors": parsed["authors"],
                "affiliation": parsed["affiliation"],
                "emails": parsed["emails"],
                "doi": parsed["doi"],
                "language": parsed["language"],
                "is_review": bool(parsed["is_review"]),
                "abstract_ro": parsed["abstract_ro"],
                "abstract_en": parsed["abstract_en"],
                "keywords_ro": parsed["keywords_ro"],
                "keywords_en": parsed["keywords_en"],
                "start_page": start_printed,
                "end_page": end_printed,
                "start_pdf_page": start_pdf,
                "end_pdf_page": end_pdf,
                "pdf_path": article_rel,
                "md_path": md_rel,
                "extract_front_source": front_source,
                "extract_first_page_source": first_page_source,
                "extract_full_source": full_source,
                "extract_quality": quality,
                "conf_title": parsed["conf_title"],
                "conf_authors": parsed["conf_authors"],
                "conf_abstract": parsed["conf_abstract"],
                "conf_keywords": parsed["conf_keywords"],
            }
        )

        if quality < 0.58:
            LOGGER.warning(
                "Low extraction quality (%s): %s (%s)",
                quality,
                entry["title"],
                issue_input["slug"],
            )

    issue_meta["article_count"] = len(processed)

    (cover_dir / "README.txt").write_text(
        "Adaugă aici coperta numărului, de exemplu: cover.jpg sau cover.png\n",
        encoding="utf-8",
    )

    write_json(meta_dir / "issue.json", issue_meta)
    write_json(meta_dir / "article_ranges.json", processed)

    (issue_dir / "README.md").write_text(
        "\n".join(
            [
                f"# {issue_input['title']}",
                "",
                f"- An: {issue_input['year']}",
                f"- Volum: {issue_input['volume']}",
                f"- Număr: {issue_input['number']}",
                f"- Pagini totale PDF: {total_pages}",
                f"- Articole detectate: {len(processed)}",
                f"- Offset pagini (TOC -> PDF): {offset}",
                "- PDF sursă: source/issue.pdf",
                "- Copertă: adaugă manual în cover/",
                "",
                "Structură:",
                "- source/: PDF număr complet",
                "- metadata/: TOC brut + metadate + intervale",
                "- articles/: PDF separat per articol",
                "- md/: fișiere Markdown per articol",
                "- cover/: folder pentru imaginea de copertă",
            ]
        ),
        encoding="utf-8",
    )

    LOGGER.info(
        "Issue processed: %s | pages=%s | entries=%s | offset=%s",
        issue_input["slug"],
        total_pages,
        len(processed),
        offset,
    )
    return issue_meta, processed


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)

    issues = resolve_issues(args.source_root, args.issue)
    if not issues:
        raise SystemExit("No issues selected for processing.")

    all_issues: list[dict] = []
    all_articles: list[dict] = []
    article_id = 1

    for issue_input in issues:
        issue_meta, entries = build_issue(issue_input)
        all_issues.append(issue_meta)

        for entry in entries:
            all_articles.append(
                {
                    "id": str(article_id),
                    "issue_id": str(issue_input["id"]),
                    "title": entry["title"],
                    "authors": entry["authors"] or entry["author"] or "N/A",
                    "affiliations": entry["affiliation"] or DEFAULT_AFFILIATION,
                    "emails": entry.get("emails", ""),
                    "abstract_ro": entry["abstract_ro"] if not entry["is_review"] else "",
                    "abstract_en": entry["abstract_en"] if not entry["is_review"] else "",
                    "keywords_ro": entry["keywords_ro"] if not entry["is_review"] else "",
                    "keywords_en": entry["keywords_en"] if not entry["is_review"] else "",
                    "pages_start": str(entry["start_page"]),
                    "pages_end": str(entry["end_page"]),
                    "doi": entry.get("doi", "") if not entry["is_review"] else "",
                    "language": entry["language"],
                    "status": "published",
                    "conf_title": f"{entry['conf_title']:.2f}",
                    "conf_authors": f"{entry['conf_authors']:.2f}",
                    "conf_keywords_ro": f"{entry['conf_keywords']:.2f}" if entry["keywords_ro"] else "0.20",
                    "conf_keywords_en": f"{entry['conf_keywords']:.2f}" if entry["keywords_en"] else "0.20",
                    "conf_abstract": f"{entry['conf_abstract']:.2f}" if (entry["abstract_ro"] or entry["abstract_en"]) else "0.20",
                    "pdf_path": entry["pdf_path"],
                    "md_path": entry["md_path"],
                    "section": entry.get("section", ""),
                    "is_review": bool(entry["is_review"]),
                    "extract_front_source": entry.get("extract_front_source", "fitz"),
                    "extract_full_source": entry.get("extract_full_source", "fitz"),
                    "extract_quality": f"{entry.get('extract_quality', 0.0):.2f}",
                }
            )
            article_id += 1

    manifest = build_global_manifest(all_issues, all_articles)

    manifest_json_path = ROOT / "ingest" / "issues_manifest.json"
    manifest_js_path = ROOT / "ingest" / "issues_manifest.js"
    manifest_json_path.parent.mkdir(parents=True, exist_ok=True)

    write_json(manifest_json_path, manifest)
    manifest_js_path.write_text(
        "window.__INGEST_MANIFEST = " + json.dumps(manifest, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )

    LOGGER.info("Generated manifest: %s", manifest_json_path)
    LOGGER.info("Issues: %s | Articles: %s", len(all_issues), len(all_articles))


if __name__ == "__main__":
    main()
