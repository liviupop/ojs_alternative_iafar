#!/usr/bin/env python3
"""
Split Series 1 & Series 2 PDFs into individual articles using the
authoritative TOC data from .md files.

Produces:
  - Individual article PDFs in each issue's articles/ directory
  - series1_manifest.js  (window.__INGEST_SERIES1)
  - series2_manifest.js  (window.__INGEST_SERIES2)
"""

import json, re, sys, unicodedata
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent.parent  # project root

# ─────────────────── Slugify ─────────────────────────────────────

def slugify(text: str, max_len: int = 80) -> str:
    """Convert text to a filesystem-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text


# ─────────────────── Series 1 parsing ────────────────────────────

SERIES1_VOLUMES = [
    {
        "toc_header": "TOC_anuar_seria1_nr1.png",
        "slug": "aaf-seria1-1932-vol-i",
        "year": "1932", "volume": "I", "number": "1",
        "title": "Anuarul Arhivei de Folklor I",
        "pdf": "BCUCLUJ_FP_490809_1932_001.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr2.png",
        "slug": "aaf-seria1-1933-vol-ii",
        "year": "1933", "volume": "II", "number": "2",
        "title": "Anuarul Arhivei de Folklor II",
        "pdf": "BCUCLUJ_FP_490809_1933_002.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr3.png",
        "slug": "aaf-seria1-1935-vol-iii",
        "year": "1935", "volume": "III", "number": "3",
        "title": "Anuarul Arhivei de Folklor III",
        "pdf": "BCUCLUJ_FP_490809_1935_003.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr4.png",
        "slug": "aaf-seria1-1937-vol-iv",
        "year": "1937", "volume": "IV", "number": "4",
        "title": "Anuarul Arhivei de Folklor IV",
        "pdf": "BCUCLUJ_FP_490809_1937_004.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr5.png",
        "slug": "aaf-seria1-1939-vol-v",
        "year": "1939", "volume": "V", "number": "5",
        "title": "Anuarul Arhivei de Folklor V",
        "pdf": "BCUCLUJ_FP_490809_1939_005.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr6.png",
        "slug": "aaf-seria1-1942-vol-vi",
        "year": "1942", "volume": "VI", "number": "6",
        "title": "Anuarul Arhivei de Folklor VI",
        "pdf": "BCUCLUJ_FP_490809_1942_006.pdf",
    },
    {
        "toc_header": "TOC_anuar_seria1_nr7.png",
        "slug": "aaf-seria1-1945-vol-vii",
        "year": "1945", "volume": "VII", "number": "7",
        "title": "Anuarul Arhivei de Folklor VII",
        "pdf": "BCUCLUJ_FP_490809_1945_007.pdf",
    },
]


def parse_series1_md(md_path: Path) -> dict[str, list[dict]]:
    """Parse Series 1 .md TOC → dict[toc_header] = [entries]."""
    text = md_path.read_text(encoding="utf-8")
    volumes = {}
    parts = re.split(r"^## (.+)$", text, flags=re.M)

    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1]
        entries = []
        current_section = ""

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("---"):
                continue

            # Section header: **BOLD TEXT**
            m_sec = re.match(r"^\*\*(.+)\*\*$", line)
            if m_sec:
                sec = m_sec.group(1).strip()
                if sec not in ("CUPRINSUL", "CUPRINS"):
                    current_section = sec
                continue

            # Entry with page number: "Title . . . . 123"
            m = re.search(r"\.\s*\.?\s*(\d+|[IVX]+)\s*$", line)
            if m:
                page_raw = m.group(1)
                # Convert Roman numerals
                try:
                    page = int(page_raw)
                except ValueError:
                    page = _roman_to_int(page_raw)

                title_text = line[: m.start()].strip().rstrip(". ")
                author, title = _split_author_title_s1(title_text)
                entries.append({
                    "section": current_section,
                    "author": author,
                    "title": title.rstrip(". "),
                    "page_start": page,
                })

        # Sort by page_start to compute page_end correctly
        # (RECENZII sections are often alphabetical, not page-ordered)
        sorted_entries = sorted(
            [e for e in entries if e.get("page_start") is not None],
            key=lambda e: e["page_start"],
        )
        no_page = [e for e in entries if e.get("page_start") is None]

        for j in range(len(sorted_entries)):
            if j + 1 < len(sorted_entries):
                # Ensure at least 1 page per article (same-start entries)
                sorted_entries[j]["page_end"] = max(
                    sorted_entries[j + 1]["page_start"] - 1,
                    sorted_entries[j]["page_start"],
                )
            else:
                sorted_entries[j]["page_end"] = None  # last entry → end of PDF

        volumes[header] = sorted_entries + no_page

    return volumes


def _split_author_title_s1(text: str) -> tuple[str, str]:
    """Split 'Author, Title text' into (author, title)."""
    # Pattern: "Name Lastname, Title..."
    m = re.match(r"^([^,]+),\s*(.+)", text)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
        words = author.split()
        if 1 <= len(words) <= 6 and all(
            w[0].isupper() or w[0] in ("'", "«", "„") or w in ("de", "și", "V.")
            for w in words if w
        ):
            return author, title
    return "", text


def _roman_to_int(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    result = 0
    for i, c in enumerate(s):
        if i + 1 < len(s) and vals.get(c, 0) < vals.get(s[i + 1], 0):
            result -= vals.get(c, 0)
        else:
            result += vals.get(c, 0)
    return result


# ─────────────────── Series 2 parsing ────────────────────────────

SERIES2_VOLUMES = [
    {
        "md_header": "Anuardefolclor_01.pdf",
        "slug": "aaf-seria2-1980-vol-i",
        "year": "1980", "volume": "I", "number": "1",
        "title": "Anuarul de Folclor I",
        "pdf": "Anuarul_de_folclor_I.pdf",
    },
    {
        "md_header": "Anuardefolclor_02.pdf",
        "slug": "aaf-seria2-1984-vol-ii",
        "year": "1984", "volume": "II", "number": "2",
        "title": "Anuarul de Folclor II",
        "pdf": "Anuarul_de_folclor_II.pdf",
    },
    {
        "md_header": "Anuardefolclor_03_04.pdf",
        "slug": "aaf-seria2-1985-1986-vol-iii-iv",
        "year": "1985-1986", "volume": "III-IV", "number": "3-4",
        "title": "Anuarul de Folclor III-IV",
        "pdf": "Anuarul_de_folclor_III-IV.pdf",
    },
    {
        "md_header": "Anuardefolclor_05_07.pdf",
        "slug": "aaf-seria2-1987-1989-vol-v-vii",
        "year": "1987-1989", "volume": "V-VII", "number": "5-7",
        "title": "Anuarul de Folclor V-VII",
        "pdf": "Anuarul_de_folclor_V-VII.pdf",
    },
    {
        "md_header": "Anuardefolclor_08_11.pdf",
        "slug": "aaf-seria2-1990-1993-vol-viii-xi",
        "year": "1990-1993", "volume": "VIII-XI", "number": "8-11",
        "title": "Anuarul Arhivei de Folclor VIII-XI",
        "pdf": "Anuarul_Arhivei_de_folclor_VIII-XI.pdf",
    },
    {
        "md_header": "Anuardefolclor_12_14.pdf",
        "slug": "aaf-seria2-1994-1995-vol-xii-xiv",
        "year": "1994-1995", "volume": "XII-XIV", "number": "12-14",
        "title": "Anuarul Arhivei de Folclor XII-XIV",
        "pdf": "Anuarul_Arhivei_de_folclor_XII-XIV.pdf",
    },
    {
        "md_header": "Anuardefolclor_15_17.pdf",
        "slug": "aaf-seria2-1996-1998-vol-xv-xvii",
        "year": "1996-1998", "volume": "XV-XVII", "number": "15-17",
        "title": "Anuarul Arhivei de Folclor XV-XVII",
        "pdf": "Anuarul_Arhivei_de_folclor_XV-XVII.pdf",
    },
]


def parse_series2_md(md_path: Path) -> dict[str, list[dict]]:
    """Parse Series 2 .md TOC → dict[md_header] = [entries]."""
    text = md_path.read_text(encoding="utf-8")
    volumes = {}

    # Split by volume headers: **Anuardefolclor_XX.pdf** or ## Anuardefolclor_XX.pdf
    parts = re.split(r"(?:^##\s+|\*\*)(Anuardefolclor_\d[\w_]*\.pdf)(?:\*\*)?", text, flags=re.M)

    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        entries = []
        current_section = ""

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("---"):
                continue

            # Section header: **BOLD TEXT**
            m_sec = re.match(r"^\*\*(.+)\*\*$", line)
            if m_sec:
                sec = m_sec.group(1).strip()
                if sec not in ("CUPRINS", "CUPRINSUL"):
                    current_section = sec
                continue

            # Skip non-entry lines (COLABORATORI, ABREVIERI as standalone)
            if re.match(r"^(COLABORATORI|ABREVIERI)\b", line):
                continue

            # Entry with page number
            m = re.search(r"\.\s*\.?\s*(\d+)\s*$", line)
            if m:
                page = int(m.group(1))
                title_text = line[: m.start()].strip().rstrip(". ")
                # Skip entries that are just "Abrevieri" or "Prefață" without author
                author, title = _split_author_title_s2(title_text, current_section)
                entries.append({
                    "section": current_section,
                    "author": author,
                    "title": title.rstrip(". "),
                    "page_start": page,
                })

            # Entry without page number (some exist for "*** Prefață")
            elif line.startswith("***"):
                cleaned = line.strip("* ").strip()
                if cleaned:
                    entries.append({
                        "section": current_section,
                        "author": "",
                        "title": cleaned,
                        "page_start": None,
                    })

        # Sort by page_start to compute page_end correctly
        # (RECENZII sections are often alphabetical, not page-ordered)
        sorted_entries = sorted(
            [e for e in entries if e.get("page_start") is not None],
            key=lambda e: e["page_start"],
        )
        no_page = [e for e in entries if e.get("page_start") is None]

        for j in range(len(sorted_entries)):
            if j + 1 < len(sorted_entries):
                sorted_entries[j]["page_end"] = max(
                    sorted_entries[j + 1]["page_start"] - 1,
                    sorted_entries[j]["page_start"],
                )
            else:
                sorted_entries[j]["page_end"] = None

        volumes[header] = sorted_entries + no_page

    return volumes


def _split_author_title_s2(text: str, section: str) -> tuple[str, str]:
    """Split author/title for Series 2 entries."""
    text = text.strip().rstrip(".")

    # RECENZII: reviewer in parentheses at end: "Book title (Reviewer Name)"
    if section in ("RECENZII",):
        m = re.search(r"\(([A-ZÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÎȘȚĂÂ][^)]{1,60})\)\s*$", text)
        if m:
            reviewer = m.group(1).strip()
            title = text[: m.start()].strip().rstrip(",. ")
            return reviewer, title

    # NOTE: also often have "(Author)" at end
    if section in ("NOTE",):
        m = re.search(r"\(([A-ZÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÎȘȚĂÂ][^)]{1,60})\)\s*$", text)
        if m:
            author = m.group(1).strip()
            title = text[: m.start()].strip().rstrip(",. ")
            return author, title

    # Regular: "Author, Title" or "Author Lastname, Title"
    m = re.match(r"^([^,]+),\s+(.+)", text)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
        words = author.split()
        if 1 <= len(words) <= 8:
            non_filler = [w for w in words if w.lower() not in ("de", "și", "von")]
            if non_filler and all(
                w[0].isupper() or w[0] in ("'", "«", "„", "†")
                for w in non_filler if w
            ):
                return author, title

    # IN MEMORIAM: "Name (dates) de Author"
    if section in ("IN MEMORIAM",):
        m = re.search(r",?\s+de\s+(.+)$", text)
        if m:
            return m.group(1).strip(), text[: m.start()].strip()
        m = re.search(r"\(([A-Z][^)]+)\)\s*$", text)
        if m:
            return m.group(1).strip(), text[: m.start()].strip()

    return "", text


# ─────────────────── PDF splitting ───────────────────────────────

def split_pdf(
    pdf_path: Path,
    entries: list[dict],
    out_dir: Path,
    total_pages: int,
    page_offset: int = 0,
) -> list[dict]:
    """Split a PDF into individual articles. Returns enriched entries."""
    doc = fitz.open(str(pdf_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.pdf"):
        stale.unlink(missing_ok=True)

    enriched = []
    for idx, entry in enumerate(entries):
        if entry.get("page_start") is None:
            continue  # Skip entries without page info

        start_page = entry["page_start"]
        end_page = entry.get("page_end") or total_pages

        # Convert TOC page labels to 0-indexed PDF pages.
        # page_offset=1 means TOC page 1 starts at PDF page index 1 (cover on first PDF page).
        pdf_start = start_page - 1 + page_offset
        pdf_end = end_page - 1 + page_offset

        if pdf_start < 0:
            pdf_start = 0
        if pdf_start >= len(doc):
            pdf_start = len(doc) - 1
        if pdf_end >= len(doc):
            pdf_end = len(doc) - 1
        if pdf_start > pdf_end:
            continue

        # Generate filename
        art_idx = len(enriched) + 1
        title_slug = slugify(entry.get("title", "untitled"))
        filename = f"{art_idx:03d}-{title_slug}.pdf"
        out_path = out_dir / filename

        # Extract pages
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=pdf_start, to_page=pdf_end)
        new_doc.save(str(out_path))
        new_doc.close()

        enriched.append({
            **entry,
            "toc_index": art_idx,
            "pdf_filename": filename,
            "pdf_start_page": pdf_start + 1,
            "pdf_end_page": pdf_end + 1,
            "pdf_pages": pdf_end - pdf_start + 1,
        })

    doc.close()
    return enriched


# ─────────────────── Manifest generation ─────────────────────────

def build_series1_manifest(series1_dir: Path, volumes: dict) -> dict:
    """Build Series 1 manifest from .md data and split PDFs."""
    issues = []
    articles = []

    for vol_def in SERIES1_VOLUMES:
        header = vol_def["toc_header"]
        entries = volumes.get(header, [])
        slug = vol_def["slug"]

        pdf_path = series1_dir / vol_def["pdf"]
        if not pdf_path.exists():
            print(f"  ⚠ PDF not found: {pdf_path}")
            continue

        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        doc.close()

        # Split
        articles_dir = series1_dir / "issues" / slug / "articles"
        # Series 1 has a cover on the first PDF page that is not counted in TOC.
        enriched = split_pdf(pdf_path, entries, articles_dir, total_pages, page_offset=1)

        issues.append({
            "slug": slug,
            "series": "seria-1",
            "series_label": "Seria I (1932-1945)",
            "year": vol_def["year"],
            "volume": vol_def["volume"],
            "number": vol_def["number"],
            "title": vol_def["title"],
            "source_pdf_name": vol_def["pdf"],
            "issue_pdf_path": f"ingest/series1/{vol_def['pdf']}",
            "article_count": len(enriched),
        })

        for e in enriched:
            articles.append({
                "issue_slug": slug,
                "series": "seria-1",
                "year": vol_def["year"],
                "volume": vol_def["volume"],
                "toc_index": e["toc_index"],
                "section": e.get("section", ""),
                "author": e.get("author", ""),
                "title": e.get("title", ""),
                "pages_start": e.get("page_start"),
                "pages_end": e.get("page_end"),
                "article_pdf_path": f"ingest/series1/issues/{slug}/articles/{e['pdf_filename']}",
            })

        print(f"  ✓ {slug}: {len(enriched)} articles from {total_pages} pages")

    return {"issues": issues, "articles": articles}


def build_series2_manifest(series2_dir: Path, volumes: dict) -> dict:
    """Build Series 2 manifest from .md data and split PDFs."""
    issues = []
    articles = []

    for vol_def in SERIES2_VOLUMES:
        header = vol_def["md_header"]
        entries = volumes.get(header, [])
        slug = vol_def["slug"]

        pdf_path = series2_dir / vol_def["pdf"]
        if not pdf_path.exists():
            print(f"  ⚠ PDF not found: {pdf_path}")
            continue

        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        doc.close()

        # Split
        articles_dir = series2_dir / "issues" / slug / "articles"
        enriched = split_pdf(pdf_path, entries, articles_dir, total_pages, page_offset=0)

        issues.append({
            "slug": slug,
            "series": "seria-2",
            "series_label": "Seria II (1980-1998)",
            "year": vol_def["year"],
            "volume": vol_def["volume"],
            "number": vol_def["number"],
            "title": vol_def["title"],
            "source_pdf_name": vol_def["pdf"],
            "issue_pdf_path": f"ingest/series2/{vol_def['pdf']}",
            "article_count": len(enriched),
        })

        for e in enriched:
            articles.append({
                "issue_slug": slug,
                "series": "seria-2",
                "year": vol_def["year"],
                "volume": vol_def["volume"],
                "toc_index": e["toc_index"],
                "section": e.get("section", ""),
                "author": e.get("author", ""),
                "title": e.get("title", ""),
                "pages_start": e.get("page_start"),
                "pages_end": e.get("page_end"),
                "article_pdf_path": f"ingest/series2/issues/{slug}/articles/{e['pdf_filename']}",
            })

        print(f"  ✓ {slug}: {len(enriched)} articles from {total_pages} pages")

    return {"issues": issues, "articles": articles}


def write_manifest_js(data: dict, out_path: Path, var_name: str):
    """Write manifest as JS with window.__INGEST_XXX = {...};"""
    js = json.dumps(data, ensure_ascii=False, indent=2)
    out_path.write_text(f"window.{var_name} = {js};\n", encoding="utf-8")
    print(f"  → {out_path} ({len(data.get('articles', []))} articles)")


# ─────────────────── Main ────────────────────────────────────────

def main():
    series1_dir = ROOT / "ingest" / "series1"
    series2_dir = ROOT / "ingest" / "series2"

    s1_md = series1_dir / "Anuar_de_folclor_seria1_TOC.md"
    s2_md = series2_dir / "TOC_Originals" / "Anuar_de_folclor_TOC_complet.md"

    print("=" * 60)
    print("Parsing Series 1 TOC from .md...")
    s1_vols = parse_series1_md(s1_md)
    total_s1 = sum(len(v) for v in s1_vols.values())
    print(f"  Found {len(s1_vols)} volumes, {total_s1} total entries")

    print("\nParsing Series 2 TOC from .md...")
    s2_vols = parse_series2_md(s2_md)
    total_s2 = sum(len(v) for v in s2_vols.values())
    print(f"  Found {len(s2_vols)} volumes, {total_s2} total entries")

    print("\n" + "=" * 60)
    print("Splitting Series 1 PDFs...")
    s1_manifest = build_series1_manifest(series1_dir, s1_vols)

    print("\n" + "=" * 60)
    print("Splitting Series 2 PDFs...")
    s2_manifest = build_series2_manifest(series2_dir, s2_vols)

    print("\n" + "=" * 60)
    print("Writing manifests...")
    write_manifest_js(s1_manifest, series1_dir / "series1_manifest.js", "__INGEST_SERIES1")
    write_manifest_js(s2_manifest, series2_dir / "series2_manifest.js", "__INGEST_SERIES2")

    print("\n✓ Done!")
    print(f"  Series 1: {len(s1_manifest['issues'])} issues, {len(s1_manifest['articles'])} articles")
    print(f"  Series 2: {len(s2_manifest['issues'])} issues, {len(s2_manifest['articles'])} articles")


if __name__ == "__main__":
    main()
