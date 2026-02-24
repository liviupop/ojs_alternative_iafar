#!/usr/bin/env python3
"""
Series 2 ingest pipeline.
Processes 7 image-only PDFs (Anuarul de folclor I-VII / Anuarul Arhivei de folclor VIII-XVII)
from the 1980-1996 period.

These scans have NO text layer — all extraction relies on OCR (tesseract).
TOC may be at the front (pages 3-8) or at the end of the PDF.
No abstracts or keywords — only author, title, section, and page range.
"""

import json, os, re, sys, unicodedata, logging
from pathlib import Path

import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("series2")

# ── Issue definitions ─────────────────────────────────────────────
# Each entry: pdf filename → slug, years, volumes, title, toc_location
ISSUES = [
    {
        "pdf": "Anuarul_de_folclor_I.pdf",
        "slug": "aaf-seria2-1980-vol-i",
        "year": "1980",
        "volume": "I",
        "number": "1",
        "title": "Anuarul de folclor I",
        "toc_pages": "end",  # TOC at end of PDF
    },
    {
        "pdf": "Anuarul_de_folclor_II.pdf",
        "slug": "aaf-seria2-1984-vol-ii",
        "year": "1984",
        "volume": "II",
        "number": "2",
        "title": "Anuarul de folclor II",
        "toc_pages": "front",
    },
    {
        "pdf": "Anuarul_de_folclor_III-IV.pdf",
        "slug": "aaf-seria2-1985-1986-vol-iii-iv",
        "year": "1985-1986",
        "volume": "III-IV",
        "number": "3-4",
        "title": "Anuarul de folclor III-IV",
        "toc_pages": "front",
    },
    {
        "pdf": "Anuarul_de_folclor_V-VII.pdf",
        "slug": "aaf-seria2-1987-1989-vol-v-vii",
        "year": "1987-1989",
        "volume": "V-VII",
        "number": "5-7",
        "title": "Anuarul de folclor V-VII",
        "toc_pages": "front",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_VIII-XI.pdf",
        "slug": "aaf-seria2-1990-1993-vol-viii-xi",
        "year": "1990-1993",
        "volume": "VIII-XI",
        "number": "8-11",
        "title": "Anuarul Arhivei de folclor VIII-XI",
        "toc_pages": "front",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XII-XIV.pdf",
        "slug": "aaf-seria2-1994-1995-vol-xii-xiv",
        "year": "1994-1995",
        "volume": "XII-XIV",
        "number": "12-14",
        "title": "Anuarul Arhivei de folclor XII-XIV",
        "toc_pages": "front",
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XV-XVII.pdf",
        "slug": "aaf-seria2-1996-1998-vol-xv-xvii",
        "year": "1996-1998",
        "volume": "XV-XVII",
        "number": "15-17",
        "title": "Anuarul Arhivei de folclor XV-XVII",
        "toc_pages": "front",
    },
]

# ── Known section headers ────────────────────────────────────────
KNOWN_SECTIONS = [
    "STUDII",
    "STUDIU",
    "CENTENARUL NAŞTERII LUI BELA BARTOK",
    "CENTENARUL NASTERII LUI BELA BARTOK",
    "ANIVERSĂRI UNESCO",
    "ANIVERSARI UNESCO",
    "ANIVERSARA",
    "ARHIVA",
    "ARHIVE FOLCLORICE",
    "IN MEMORIAM",
    "RECENZII",
    "NOTE",
    "SISTEMATICA TIPOLOGICA",
    "SISTEMATICA. TIPOLOGICA",
    "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIE",
    "CONTRIBUTII DE ISTORIE A FOLCLORISTICII SI ETNOGRAFIE",
    "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIEI",
    "MATERIALE SI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE",
    "MATERIALE ȘI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE",
    "ALTERNATIVA",
]

# Canonical mapping (OCR variants → normalized)
SECTION_CANONICAL = {
    "STUDIU": "STUDII",
    "SISTEMATICA. TIPOLOGICA": "SISTEMATICĂ TIPOLOGICĂ",
    "SISTEMATICA TIPOLOGICA": "SISTEMATICĂ TIPOLOGICĂ",
    "CENTENARUL NASTERII LUI BELA BARTOK": "CENTENARUL NAŞTERII LUI BÉLA BARTÓK",
    "CENTENARUL NAŞTERII LUI BELA BARTOK": "CENTENARUL NAŞTERII LUI BÉLA BARTÓK",
    "ANIVERSARI UNESCO": "ANIVERSĂRI UNESCO",
    "ARHIVE FOLCLORICE": "ARHIVE FOLCLORICE",
    "CONTRIBUTII DE ISTORIE A FOLCLORISTICII SI ETNOGRAFIE": "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIEI",
    "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIE": "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIEI",
    "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIEI": "CONTRIBUȚII DE ISTORIE A FOLCLORISTICII ȘI ETNOGRAFIEI",
    "MATERIALE SI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE": "MATERIALE ȘI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE",
    "MATERIALE ȘI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE": "MATERIALE ȘI CONTRIBUȚII LA ISTORIA ȘTIINȚELOR ETNOLOGICE",
}


def slugify(text: str, max_len: int = 80) -> str:
    """Create a URL-safe slug from text."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:max_len]


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


def extract_pdf_index(name: str) -> int | None:
    m = re.match(r"^(\d+)-", name or "")
    return int(m.group(1)) if m else None


def title_from_pdf_name(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\d+-", "", stem)
    stem = stem.replace("-", " ").strip()
    return clean_display_text(stem)


def ocr_page(doc, page_idx: int, dpi: int = 250) -> str:
    """OCR a single page from a fitz document."""
    from PIL import Image
    import pytesseract, io
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang="ron+deu")


def find_toc_pages(doc, toc_hint: str) -> list[int]:
    """Find pages containing the Romanian TOC (CUPRINS)."""
    total = len(doc)
    candidates = []

    if toc_hint == "front":
        search_range = range(min(10, total))
    elif toc_hint == "end":
        search_range = list(range(max(0, total - 15), total))
    else:
        search_range = list(range(min(10, total))) + list(range(max(0, total - 15), total))

    for pg in search_range:
        txt = ocr_page(doc, pg, dpi=200)
        if "CUPRINS" in txt.upper():
            candidates.append(pg)
            # Also grab next 2-3 pages as continuation
            for extra in range(1, 4):
                if pg + extra < total:
                    next_txt = ocr_page(doc, pg + extra, dpi=200)
                    # Stop if we hit INHALT (German TOC) or COLLABORATORI
                    upper = next_txt.upper()
                    if "INHALT" in upper or "CONTENTS" in upper or "SOMMAIRE" in upper:
                        break
                    # Still part of CUPRINS if it has page numbers and article-like text
                    if re.search(r"\d{2,3}", next_txt):
                        candidates.append(pg + extra)
            break

    return sorted(set(candidates))


def parse_toc_text(toc_text: str) -> list[dict]:
    """Parse OCR'd TOC text into structured entries with sections."""
    entries = []
    current_section = ""

    # Clean up OCR artifacts
    lines = toc_text.split("\n")

    # Track page numbers separately — they often appear on their own lines
    # or at the end of title lines
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Skip non-TOC lines
        upper = line.upper().strip()
        if upper in ("CUPRINS", "INHALT", "CONTENTS", "SOMMAIRE",
                      "CONTENTS | SOMMAIRE | INHALT",
                      "CONTENTS/SOMMAIRE/INHALT",
                      "COLABORATORI", "LISTA COLABORATORILOR",
                      "ABREVIERI", "ABREVIERE"):
            continue

        # Check if this is a section header
        is_section = False
        for known in KNOWN_SECTIONS:
            if upper.startswith(known) or known in upper:
                # Avoid false positive: "RECENZII 361" is section + page
                clean = re.sub(r"\d+\s*$", "", upper).strip()
                for k2 in KNOWN_SECTIONS:
                    if clean == k2 or k2 in clean:
                        canonical = SECTION_CANONICAL.get(k2, k2)
                        current_section = canonical
                        is_section = True
                        break
                if is_section:
                    break

        if is_section:
            continue

        # Skip pure page numbers
        if re.match(r"^\d{1,3}[\s,]*$", line):
            continue

        # Skip lines that are just page headers like "4 Cuprins" or "Cuprins 5"
        if re.match(r"^\d+\s+[Cc]uprins", line) or re.match(r"[Cc]uprins\s+\d+", line):
            continue

        # Try to extract author + title + page from a TOC line
        entry = _parse_toc_line(line, current_section)
        if entry:
            entries.append(entry)

    return entries


def _parse_toc_line(line: str, section: str) -> dict | None:
    """Parse a single TOC line into author, title, page_start."""
    # Common pattern: "Author Name, Title text . . . . 123"
    # Or: "Author Name, Title text (Reviewer Name) . . . 123"

    # Extract trailing page number
    page_match = re.search(r"[\s.]+(\d{1,4})\s*$", line)
    page_start = None
    if page_match:
        page_start = int(page_match.group(1))
        line = line[:page_match.start()].strip()

    # Remove trailing dots and spaces
    line = re.sub(r"[\s.]+$", "", line).strip()

    if not line or len(line) < 5:
        return None

    # Skip lines that look like continuation of previous entries
    # (start with lowercase, or are very short fragments)
    if line[0].islower() and not line.startswith("de "):
        return None

    # For RECENZII section: title is the book citation, author is in parentheses
    if section in ("RECENZII", "NOTE"):
        # Pattern: "Book Author, Book Title, City, Year (Reviewer Name)"
        reviewer_match = re.search(r"\(([^)]+)\)\s*$", line)
        reviewer = ""
        if reviewer_match:
            reviewer = reviewer_match.group(1).strip()
            line = line[:reviewer_match.start()].strip()
            line = re.sub(r"[\s.]+$", "", line).strip()

        return {
            "section": section,
            "author": reviewer if reviewer else "",
            "title": line,
            "page_start": page_start,
        }

    # For regular articles: "Author, Title"
    # Try to split on first comma after what looks like a name
    # Name patterns: "Ion Talos", "Hanni Markel și Gabriela Vőő"
    comma_match = re.search(r"^([^,]+),\s*(.+)", line)
    if comma_match:
        potential_author = comma_match.group(1).strip()
        potential_title = comma_match.group(2).strip()

        # Verify it looks like an author name (2-4 words, capitalized)
        words = potential_author.split()
        if 1 <= len(words) <= 6 and all(w[0].isupper() or w in ("de", "și", "si", "und") for w in words if w):
            return {
                "section": section,
                "author": potential_author,
                "title": potential_title,
                "page_start": page_start,
            }

    # If no comma split works, try "Author Name  Title" (double space)
    # Or the whole line is just a title (e.g., "Prefața")
    if line.startswith("Prefat") or line.startswith("Prefaţ"):
        return {
            "section": "",
            "author": "",
            "title": "Prefață",
            "page_start": page_start,
        }

    # Fallback: treat whole line as title with no author
    return {
        "section": section,
        "author": "",
        "title": line,
        "page_start": page_start,
    }


def infer_page_ends(entries: list[dict], total_pages: int) -> list[dict]:
    """Infer page_end for each entry based on next entry's page_start."""
    for i, entry in enumerate(entries):
        if i + 1 < len(entries) and entries[i + 1].get("page_start"):
            entry["page_end"] = entries[i + 1]["page_start"] - 1
        else:
            entry["page_end"] = None  # Last entry or unknown
    return entries


def find_cover_offset(doc, first_article_page: int) -> int:
    """Find the PDF page offset (0-indexed) for labeled page 1.

    For scanned volumes, the PDF page numbers don't match the printed page numbers.
    We OCR the area around where page 1 should be and look for matching content.
    """
    # Try a range of offsets and see which one puts us near page content
    # Most volumes have 5-15 pages of front matter before page 1
    total = len(doc)
    best_offset = 0

    # OCR the footer area of candidate pages to find page numbers
    from PIL import Image
    import pytesseract, io

    for candidate_offset in range(0, min(20, total)):
        page = doc[candidate_offset]
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # Crop bottom 15% for page number
        w, h = img.size
        footer = img.crop((0, int(h * 0.85), w, h))
        footer_txt = pytesseract.image_to_string(footer, lang="ron+deu")

        # Look for page number in footer
        nums = re.findall(r"\b(\d{1,3})\b", footer_txt)
        for n in nums:
            if int(n) == first_article_page:
                return candidate_offset - first_article_page

    # Fallback: try matching by header OCR
    for candidate_offset in range(0, min(20, total)):
        page = doc[candidate_offset]
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # Crop top 15% for header with page number
        w, h = img.size
        header = img.crop((0, 0, w, int(h * 0.15)))
        header_txt = pytesseract.image_to_string(header, lang="ron+deu")
        nums = re.findall(r"\b(\d{1,3})\b", header_txt)
        for n in nums:
            if int(n) == first_article_page:
                return candidate_offset - first_article_page

    return best_offset


def split_articles(doc, entries: list[dict], cover_offset: int, output_dir: Path):
    """Split the PDF into individual article PDFs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(doc)

    for i, entry in enumerate(entries):
        if entry.get("page_start") is None:
            log.warning(f"  Skipping entry {i+1} (no page_start): {entry.get('title', '?')[:50]}")
            continue

        start_pdf_page = entry["page_start"] + cover_offset
        if entry.get("page_end"):
            end_pdf_page = entry["page_end"] + cover_offset
        else:
            # Last article: go to end (minus collaborators/abbreviations)
            end_pdf_page = total - 1

        # Clamp
        start_pdf_page = max(0, min(start_pdf_page, total - 1))
        end_pdf_page = max(start_pdf_page, min(end_pdf_page, total - 1))

        idx = str(i + 1).zfill(3)
        title_slug = slugify(entry.get("title", "untitled"))
        filename = f"{idx}-{title_slug}.pdf"

        out_doc = fitz.open()
        out_doc.insert_pdf(doc, from_page=start_pdf_page, to_page=end_pdf_page)
        out_path = output_dir / filename
        out_doc.save(str(out_path))
        out_doc.close()

        entry["article_pdf"] = filename
        entry["pdf_page_start"] = start_pdf_page
        entry["pdf_page_end"] = end_pdf_page

        log.info(f"  [{idx}] pp.{entry['page_start']}-{entry.get('page_end','?')} "
                 f"→ PDF:{start_pdf_page}-{end_pdf_page} | {filename[:60]}")


def process_issue(issue_def: dict, series2_dir: Path, output_base: Path,
                  toc_override: str = None) -> dict:
    """Process a single Series 2 issue."""
    pdf_path = series2_dir / issue_def["pdf"]
    if not pdf_path.exists():
        log.error(f"PDF not found: {pdf_path}")
        return {"error": f"PDF not found: {pdf_path}"}

    slug = issue_def["slug"]
    issue_dir = output_base / slug
    articles_dir = issue_dir / "articles"
    metadata_dir = issue_dir / "metadata"
    articles_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"\n{'='*60}")
    log.info(f"Processing: {issue_def['title']} ({issue_def['year']})")
    log.info(f"PDF: {pdf_path.name}")
    log.info(f"{'='*60}")

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    log.info(f"Total pages: {total_pages}")

    # Step 1: Get TOC text
    if toc_override:
        toc_text = toc_override
        log.info("Using provided TOC text override")
    else:
        log.info("Finding TOC pages via OCR...")
        toc_page_idxs = find_toc_pages(doc, issue_def.get("toc_pages", "both"))
        if not toc_page_idxs:
            log.error("Could not find CUPRINS page!")
            doc.close()
            return {"error": "No CUPRINS found"}

        log.info(f"TOC found on pages: {[p+1 for p in toc_page_idxs]}")
        toc_text = ""
        for pg_idx in toc_page_idxs:
            toc_text += ocr_page(doc, pg_idx) + "\n"

    # Step 2: Parse TOC
    log.info("Parsing TOC entries...")
    entries = parse_toc_text(toc_text)
    entries = infer_page_ends(entries, total_pages)

    log.info(f"Found {len(entries)} TOC entries")
    for e in entries:
        section_tag = f"[{e['section']}] " if e['section'] else ""
        log.info(f"  {section_tag}{e.get('author', '')} — {e.get('title', '')[:60]} (p.{e.get('page_start', '?')})")

    if not entries:
        log.error("No entries parsed from TOC!")
        doc.close()
        return {"error": "No TOC entries parsed"}

    # Step 3: Find cover offset
    first_page = None
    for e in entries:
        if e.get("page_start"):
            first_page = e["page_start"]
            break

    if first_page:
        log.info(f"Finding cover offset (first article page label: {first_page})...")
        cover_offset = find_cover_offset(doc, first_page)
        log.info(f"Cover offset: {cover_offset}")
    else:
        cover_offset = 0
        log.warning("No page numbers found, using offset 0")

    # Step 4: Split articles
    log.info("Splitting articles...")
    split_articles(doc, entries, cover_offset, articles_dir)

    # Step 5: Write metadata
    toc_entries = []
    for i, e in enumerate(entries):
        toc_entries.append({
            "index": i + 1,
            "section": e.get("section", ""),
            "author": e.get("author", ""),
            "title": e.get("title", ""),
            "page_start_label": str(e["page_start"]) if e.get("page_start") else "",
            "page_start": e.get("page_start"),
            "page_end": e.get("page_end"),
        })

    issue_meta = {
        "slug": slug,
        "series": "seria-2",
        "series_label": "Seria II (1980-1998)",
        "year": issue_def["year"],
        "volume": issue_def["volume"],
        "number": issue_def["number"],
        "title": issue_def["title"],
        "source_pdf_name": issue_def["pdf"],
    }

    toc_path = metadata_dir / "toc_entries.json"
    issue_path = metadata_dir / "issue.json"

    with open(toc_path, "w", encoding="utf-8") as f:
        json.dump(toc_entries, f, ensure_ascii=False, indent=2)

    with open(issue_path, "w", encoding="utf-8") as f:
        json.dump(issue_meta, f, ensure_ascii=False, indent=2)

    doc.close()

    log.info(f"\nWrote {len(toc_entries)} entries to {toc_path}")
    log.info(f"Wrote issue metadata to {issue_path}")

    return {
        "slug": slug,
        "entries": len(toc_entries),
        "articles_dir": str(articles_dir),
    }


def build_manifest(output_base: Path, manifest_path: Path):
    """Build series2 manifest from split article PDFs + TOC metadata."""
    issues = []
    articles = []

    for issue_dir in sorted(output_base.iterdir()):
        if not issue_dir.is_dir():
            continue
        issue_json = issue_dir / "metadata" / "issue.json"
        toc_json = issue_dir / "metadata" / "toc_entries.json"
        articles_dir = issue_dir / "articles"

        if not issue_json.exists() or not toc_json.exists():
            continue

        with open(issue_json, "r", encoding="utf-8") as f:
            issue_meta = json.load(f)
        with open(toc_json, "r", encoding="utf-8") as f:
            toc_entries = json.load(f)

        toc_by_index = {
            int(entry.get("index")): entry
            for entry in toc_entries
            if isinstance(entry.get("index"), int)
        }

        split_files = []
        if articles_dir.exists():
            for pdf_file in sorted(articles_dir.glob("*.pdf")):
                idx = extract_pdf_index(pdf_file.name)
                if idx is not None:
                    split_files.append((idx, pdf_file.name))
        split_files.sort(key=lambda x: x[0])

        source_pdf_name = str(issue_meta.get("source_pdf_name", "")).strip()
        issue_item = dict(issue_meta)
        issue_item["series"] = "seria-2"
        issue_item["series_label"] = "Seria II (1980-1998)"
        issue_item["issue_pdf_path"] = f"ingest/series2/{source_pdf_name}" if source_pdf_name else ""
        issue_item["article_count"] = len(split_files)
        issues.append(issue_item)

        for idx, file_name in split_files:
            entry = toc_by_index.get(idx, {})
            title = clean_display_text(entry.get("title", "")) or title_from_pdf_name(file_name)
            author = clean_display_text(entry.get("author", ""))
            section = clean_display_text(entry.get("section", ""))

            page_start = entry.get("page_start")
            page_end = entry.get("page_end")
            if not isinstance(page_start, int) or page_start <= 0 or page_start > 1500:
                page_start = None
            if not isinstance(page_end, int) or page_end <= 0 or page_end > 1500:
                page_end = None
            if page_start and page_end and page_end < page_start:
                page_end = None

            articles.append({
                "issue_slug": issue_item["slug"],
                "index": idx,
                "section": section,
                "author": author,
                "title": title,
                "page_start": page_start,
                "page_end": page_end,
                "article_pdf_path": f"ingest/series2/issues/{issue_item['slug']}/articles/{file_name}",
            })

    issues.sort(
        key=lambda issue: (
            parse_first_year(issue.get("year", "")),
            parse_first_year(issue.get("volume", "")),
            issue.get("slug", ""),
        ),
        reverse=True,
    )
    issue_order = {iss.get("slug", ""): idx for idx, iss in enumerate(issues)}
    articles.sort(key=lambda art: (issue_order.get(art.get("issue_slug", ""), 10_000), art.get("index", 0)))

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


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Series 2 ingest pipeline")
    parser.add_argument("--series2-dir", default="ingest/series2",
                        help="Directory containing Series 2 source PDFs")
    parser.add_argument("--output-dir", default="ingest/series2/issues",
                        help="Output directory for processed issues")
    parser.add_argument("--toc-dir", default=None,
                        help="Directory with pre-extracted TOC text files")
    parser.add_argument("--issue", default=None,
                        help="Process only this issue slug (or index 1-7)")
    parser.add_argument("--manifest-only", action="store_true",
                        help="Only regenerate the manifest from existing data")
    parser.add_argument("--manifest-path", default="ingest/series2/series2_manifest.js",
                        help="Output path for the JS manifest")

    args = parser.parse_args()

    series2_dir = Path(args.series2_dir)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest_path)

    if args.manifest_only:
        build_manifest(output_dir, manifest_path)
        sys.exit(0)

    # Pre-extracted TOC files (from OCR agent)
    toc_overrides = {}
    if args.toc_dir:
        toc_dir = Path(args.toc_dir)
        toc_files = {
            "Anuarul_de_folclor_I.pdf": "01_vol_I_toc.txt",
            "Anuarul_de_folclor_II.pdf": "02_vol_II_toc.txt",
            "Anuarul_de_folclor_III-IV.pdf": "03_vol_III-IV_toc.txt",
            "Anuarul_de_folclor_V-VII.pdf": "04_vol_V-VII_toc.txt",
            "Anuarul_Arhivei_de_folclor_VIII-XI.pdf": "05_vol_VIII-XI_toc.txt",
            "Anuarul_Arhivei_de_folclor_XII-XIV.pdf": "06_vol_XII-XIV_toc.txt",
            "Anuarul_Arhivei_de_folclor_XV-XVII.pdf": "07_vol_XV-XVII_toc.txt",
        }
        for pdf_name, toc_file in toc_files.items():
            toc_path = toc_dir / toc_file
            if toc_path.exists():
                with open(toc_path, "r", encoding="utf-8") as f:
                    toc_overrides[pdf_name] = f.read()

    issues_to_process = ISSUES
    if args.issue:
        try:
            idx = int(args.issue) - 1
            issues_to_process = [ISSUES[idx]]
        except (ValueError, IndexError):
            issues_to_process = [i for i in ISSUES if i["slug"] == args.issue]

    results = []
    for issue_def in issues_to_process:
        toc_text = toc_overrides.get(issue_def["pdf"])
        result = process_issue(issue_def, series2_dir, output_dir, toc_override=toc_text)
        results.append(result)

    # Build manifest
    build_manifest(output_dir, manifest_path)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    for r in results:
        if "error" in r:
            log.error(f"  FAILED: {r['error']}")
        else:
            log.info(f"  {r['slug']}: {r['entries']} entries")
