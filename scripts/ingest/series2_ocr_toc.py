#!/usr/bin/env python3
"""
High-quality TOC extraction for Series 2 PDFs.

Strategy — dual-crop OCR:
1. Crop each CUPRINS page into LEFT (78%) and RIGHT (22%) regions
2. LEFT → `image_to_string` for clean text preserving line order
3. RIGHT → `image_to_data` for page-number bounding boxes with y-coords
4. Also `image_to_data` on LEFT to get y-coords per text line
5. Match page numbers to text lines by y-coordinate proximity
6. Parse structured entries (section, author, title, page_start)

This gives far better results than full-page OCR because the
two-column layout (text + dots + page numbers) confuses tesseract.
"""

import json, re, sys, logging
from pathlib import Path
from dataclasses import dataclass

import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("series2_ocr")

# ── Issue definitions ─────────────────────────────────────────────
ISSUES = [
    {
        "pdf": "Anuarul_de_folclor_I.pdf",
        "slug": "aaf-seria2-1980-vol-i",
        "toc_page_indices": [259, 260],  # pages 260-261
    },
    {
        "pdf": "Anuarul_de_folclor_II.pdf",
        "slug": "aaf-seria2-1984-vol-ii",
        "toc_page_indices": [2, 3, 4],  # pages 3-5
    },
    {
        "pdf": "Anuarul_de_folclor_III-IV.pdf",
        "slug": "aaf-seria2-1985-1986-vol-iii-iv",
        "toc_page_indices": [4, 5, 6],  # pages 5-7
    },
    {
        "pdf": "Anuarul_de_folclor_V-VII.pdf",
        "slug": "aaf-seria2-1987-1989-vol-v-vii",
        "toc_page_indices": [4, 5, 6],  # pages 5-7
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_VIII-XI.pdf",
        "slug": "aaf-seria2-1990-1993-vol-viii-xi",
        "toc_page_indices": [3, 4, 5],  # pages 4-6
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XII-XIV.pdf",
        "slug": "aaf-seria2-1994-1995-vol-xii-xiv",
        "toc_page_indices": [4, 5, 6],  # pages 5-7
    },
    {
        "pdf": "Anuarul_Arhivei_de_folclor_XV-XVII.pdf",
        "slug": "aaf-seria2-1996-1998-vol-xv-xvii",
        "toc_page_indices": [4, 5, 6],  # pages 5-7
    },
]

# ── Section headers ──────────────────────────────────────────────
SECTION_PATTERNS = [
    (r"^STUDII?\b", "STUDII"),
    (r"^CENTENARUL\b", "CENTENARUL NAŞTERII LUI BÉLA BARTÓK"),
    (r"^ANIVERSAR[IĂ]\b", "ANIVERSĂRI"),
    (r"^ARHIV[AĂE]\b", "ARHIVĂ"),
    (r"^ARHIVE\s+FOLCLORICE", "ARHIVE FOLCLORICE"),
    (r"^IN\s+MEMORIAM", "IN MEMORIAM"),
    (r"^RECENZI", "RECENZII"),
    (r"^NOTE\b", "NOTE"),
    (r"^SISTEMATIC[AĂ]", "SISTEMATICĂ TIPOLOGICĂ"),
    (r"^CONTRIBU[TŢȚÎ]II\b", "CONTRIBUȚII LA ISTORIA FOLCLORISTICII"),
    (r"^MATERIALE\b", "MATERIALE ȘI CONTRIBUȚII"),
    (r"^ALTERNATIVA\b", "ALTERNATIVA"),
]

STOP_MARKERS = [
    "INHALT", "CONTENTS", "SOMMAIRE", "ABHANDLUNGEN",
    "CONTENTS/SOMMAIRE", "CONTENTS | SOMMAIRE",
    "COLABORATORI", "LISTA COLABORATORILOR",
    "VERZEICHNIS", "MITARBEITER",
]

NOISE_PATTERNS = [
    r"^CUPRINS$", r"^PAG\.?$", r"^\d+\s*$",
    r"^\d+\s+[Cc]uprins", r"[Cc]uprins\s+\d+",
    r"^[\s.·_\-|]+$", r"^Abrevie",
]


# ── Core OCR ─────────────────────────────────────────────────────

def ocr_cuprins_page(doc, page_idx: int, dpi: int = 300,
                     text_frac: float = 0.78) -> list[dict]:
    """OCR one CUPRINS page with dual-crop strategy.

    Returns list of dicts: {text: str, y: int, page_num: int|None}
    """
    from PIL import Image
    import pytesseract, io

    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    W, H = img.size
    split_x = int(W * text_frac)

    # ── Left crop: text ──
    text_img = img.crop((0, 0, split_x, H))
    text_str = pytesseract.image_to_string(text_img, lang="ron+deu",
                                           config="--oem 3 --psm 4")

    # Get y-coordinates for each text line via image_to_data
    text_data = pytesseract.image_to_data(
        text_img, lang="ron+deu", output_type=pytesseract.Output.DICT,
        config="--oem 3 --psm 4"
    )
    # Build a mapping: line text → approximate y (from first word of line)
    line_y_map = _build_line_y_map(text_str, text_data)

    # ── Right crop: page numbers ──
    nums_img = img.crop((split_x, 0, W, H))
    nums_data = pytesseract.image_to_data(
        nums_img, lang="eng", output_type=pytesseract.Output.DICT
    )

    page_nums = []  # (y, number)
    for i, word in enumerate(nums_data["text"]):
        word = word.strip()
        if not word:
            continue
        # Clean common OCR substitutions
        clean = word.replace("O", "0").replace("o", "0").replace("l", "1")
        clean = re.sub(r"[^0-9]", "", clean)
        if clean and 1 <= int(clean) <= 999:
            page_nums.append((nums_data["top"][i], int(clean)))

    log.info(f"    Page {page_idx+1}: {len(line_y_map)} text lines, "
             f"{len(page_nums)} page numbers")

    # ── Match ──
    results = []
    text_lines = text_str.strip().split("\n")

    for line_text in text_lines:
        line_text = line_text.strip()
        if not line_text:
            continue

        y = line_y_map.get(line_text)
        matched_num = _match_page_num(y, page_nums, tolerance=35) if y else None

        results.append({
            "text": line_text,
            "y": y or 0,
            "page_num": matched_num,
        })

    return results


def _build_line_y_map(text_str: str, data: dict) -> dict[str, int]:
    """Build mapping from text line → y coordinate."""
    # Strategy: find the first few words of each line in the data,
    # return their y coordinate.
    mapping = {}
    lines = text_str.strip().split("\n")

    # Build word list from data with positions
    words_with_pos = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if word:
            words_with_pos.append((word, data["top"][i], data["left"][i]))

    word_idx = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue

        first_word = line.split()[0] if line.split() else ""
        if not first_word:
            continue

        # Find this word in the remaining data words
        for j in range(word_idx, len(words_with_pos)):
            if words_with_pos[j][0] == first_word:
                mapping[line] = words_with_pos[j][1]
                word_idx = j + 1
                break
        else:
            # Fuzzy match — first 3 chars
            for j in range(word_idx, min(word_idx + 30, len(words_with_pos))):
                if words_with_pos[j][0][:3] == first_word[:3]:
                    mapping[line] = words_with_pos[j][1]
                    word_idx = j + 1
                    break

    return mapping


def _match_page_num(y: int, page_nums: list[tuple[int, int]],
                    tolerance: int = 35) -> int | None:
    """Find the page number closest to y within tolerance."""
    if not page_nums or y is None:
        return None

    best_num = None
    best_dist = tolerance + 1

    for pn_y, pn_val in page_nums:
        dist = abs(pn_y - y)
        if dist < best_dist:
            best_dist = dist
            best_num = pn_val

    return best_num


# ── Parsing ──────────────────────────────────────────────────────

def parse_toc_lines(lines: list[dict]) -> list[dict]:
    """Parse OCR'd TOC lines into structured entries."""
    entries = []
    current_section = ""
    pending_author = ""
    pending_title = ""
    pending_page = None

    for line in lines:
        text = line["text"].strip()
        if not text:
            continue

        upper = text.upper().strip()

        # Stop at German/English/French TOC
        if any(s in upper for s in STOP_MARKERS):
            _flush(entries, current_section, pending_author, pending_title, pending_page)
            break

        # Skip noise
        if any(re.match(p, upper) or re.match(p, text) for p in NOISE_PATTERNS):
            continue

        # Section header?
        section_match = None
        for pattern, section_name in SECTION_PATTERNS:
            if re.search(pattern, upper):
                section_match = section_name
                break
        if section_match:
            _flush(entries, current_section, pending_author, pending_title, pending_page)
            pending_author = pending_title = ""
            pending_page = None
            current_section = section_match
            continue

        # Is this a new entry or continuation?
        if _is_new_entry(text, current_section):
            _flush(entries, current_section, pending_author, pending_title, pending_page)
            pending_author, pending_title = _split_author_title(text, current_section)
            pending_page = line.get("page_num")
        else:
            # Continuation
            cont = _clean_continuation(text)
            if cont:
                pending_title = (pending_title + " " + cont) if pending_title else cont
            if line.get("page_num") and pending_page is None:
                pending_page = line["page_num"]

    # Final flush
    _flush(entries, current_section, pending_author, pending_title, pending_page)

    # Infer page_end
    for i in range(len(entries)):
        if i + 1 < len(entries) and entries[i + 1].get("page_start"):
            entries[i]["page_end"] = entries[i + 1]["page_start"] - 1
        else:
            entries[i]["page_end"] = None

    return entries


def _flush(entries, section, author, title, page):
    if title:
        entries.append(_make_entry(section, author, title, page))


def _is_new_entry(text: str, section: str) -> bool:
    """Determine if this text starts a new TOC entry."""
    # Pattern: "Author Name, Title..."
    if re.match(r"^[A-ZĂÂÎȘȚÜÖÉÈÊËÀÁÓÚ][a-zăâîșțüöéèêëàáóúvV]+\s+[A-ZĂÂÎȘȚÜÖÉÈÊËÀÁÓÚ]", text):
        return True
    # "A. B. Name, Title"
    if re.match(r"^[A-Z]\.\s*[A-Z]", text):
        return True
    # IN MEMORIAM entries start with name + dates
    if section == "IN MEMORIAM" and re.match(r"^[A-Z]", text):
        return True
    # "Prefață"
    if re.match(r"^Prefat[aăä]", text, re.I):
        return True
    # NOTE/RECENZII: entries usually start capitalized
    if section in ("NOTE", "RECENZII") and re.match(r"^[A-ZĂÂÎȘȚÜÖÉ]", text):
        return True
    return False


def _split_author_title(text: str, section: str) -> tuple[str, str]:
    """Split into (author, title)."""
    text = re.sub(r"\s*\.{2,}\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # RECENZII / NOTE: reviewer in parentheses at end
    if section in ("RECENZII", "NOTE"):
        m = re.search(r"\(([A-Z][^)]{1,50})\)\s*[\.\s]*$", text)
        if m:
            reviewer = m.group(1).strip()
            title = text[:m.start()].strip().rstrip(".")
            return reviewer, title
        # Some notes have author + short title format
        # Try comma split anyway
        pass

    # Regular: "Author, Title"
    m = re.match(r"^([^,]+),\s*(.+)", text)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
        words = author.split()
        # Verify author-like: 2-6 capitalized words
        if 1 <= len(words) <= 8:
            non_filler = [w for w in words if w.lower() not in ("de", "și", "si", "und", "|", "†")]
            if non_filler and all(w[0].isupper() or w[0] == "'" for w in non_filler if w):
                return author, title

    # IN MEMORIAM: "Name (dates) de Author" or "(Author)"
    if section == "IN MEMORIAM":
        m = re.search(r"\bde\s+(.+)$", text)
        if m:
            return m.group(1).strip(), text[:m.start()].strip()
        m = re.search(r"\(([A-Z][^)]+)\)\s*$", text)
        if m:
            return m.group(1).strip(), text[:m.start()].strip()

    return "", text


def _clean_continuation(text: str) -> str:
    """Clean a continuation line."""
    text = re.sub(r"^[\s.·_\-|!]+", "", text)
    text = re.sub(r"[\s.·_\-|!]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _make_entry(section: str, author: str, title: str, page_start: int | None) -> dict:
    title = re.sub(r"\s*\.{2,}\s*", " ", title)
    title = re.sub(r"[\s.·_|]+$", "", title)
    title = re.sub(r"^\s*[\-\.,:;|]+\s*", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    author = re.sub(r"\s*\.{2,}\s*", " ", author)
    author = re.sub(r"[\s.|]+$", "", author)
    author = re.sub(r"\s+", " ", author).strip()

    # Fix common OCR issues in page numbers
    # 465 → 165 (4 misread as 1 for numbers in expected range)
    if page_start and page_start >= 400 and str(page_start)[0] == "4":
        corrected = int("1" + str(page_start)[1:])
        if 100 <= corrected <= 300:
            page_start = corrected

    return {
        "section": section,
        "author": author,
        "title": title,
        "page_start": page_start,
    }


# ── Main ─────────────────────────────────────────────────────────

def extract_toc(doc, toc_page_indices: list[int], dpi: int = 300) -> list[dict]:
    """Full extraction pipeline for one issue."""
    all_lines = []

    for pg_idx in toc_page_indices:
        if pg_idx >= len(doc):
            continue
        log.info(f"  OCR page {pg_idx+1} at {dpi} DPI (dual-crop)...")
        page_lines = ocr_cuprins_page(doc, pg_idx, dpi=dpi)

        # Check for stop markers
        hit_stop = False
        for pl in page_lines:
            if any(s in pl["text"].upper() for s in STOP_MARKERS):
                hit_stop = True
                break
            all_lines.append(pl)

        if hit_stop:
            log.info(f"    Reached foreign-language TOC, stopping")
            break

    return parse_toc_lines(all_lines)


def process_all(series2_dir: Path, output_dir: Path, dpi: int = 300):
    """Process all 7 issues."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for issue_def in ISSUES:
        pdf_path = series2_dir / issue_def["pdf"]
        if not pdf_path.exists():
            log.error(f"PDF not found: {pdf_path}")
            continue

        slug = issue_def["slug"]
        log.info(f"\n{'='*60}")
        log.info(f"Processing: {slug}")
        log.info(f"TOC pages: {[p+1 for p in issue_def['toc_page_indices']]}")
        log.info(f"{'='*60}")

        doc = fitz.open(str(pdf_path))
        entries = extract_toc(doc, issue_def["toc_page_indices"], dpi=dpi)
        doc.close()

        log.info(f"\n  {len(entries)} entries:")
        for i, e in enumerate(entries, 1):
            sec = f"[{e['section']}] " if e.get('section') else ""
            auth = f"{e['author']} — " if e.get('author') else ""
            pg = f" (p.{e['page_start']})" if e.get('page_start') else " (NO PAGE)"
            log.info(f"  {i:3d}. {sec}{auth}{e['title'][:65]}{pg}")

        # Save
        issue_out = output_dir / slug
        issue_out.mkdir(parents=True, exist_ok=True)
        toc_path = issue_out / "toc_entries_ocr.json"

        # Convert to final format with index
        final_entries = []
        for i, e in enumerate(entries, 1):
            final_entries.append({
                "index": i,
                "section": e.get("section", ""),
                "author": e.get("author", ""),
                "title": e.get("title", ""),
                "page_start_label": str(e["page_start"]) if e.get("page_start") else "",
                "page_start": e.get("page_start"),
                "page_end": e.get("page_end"),
            })

        with open(toc_path, "w", encoding="utf-8") as f:
            json.dump(final_entries, f, ensure_ascii=False, indent=2)
        log.info(f"  → {toc_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--series2-dir", default="ingest/series2")
    parser.add_argument("--output-dir", default="ingest/series2/issues")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--issue", type=int, default=None, help="1-7")
    args = parser.parse_args()

    if args.issue:
        issue_def = ISSUES[args.issue - 1]
        doc = fitz.open(str(Path(args.series2_dir) / issue_def["pdf"]))
        entries = extract_toc(doc, issue_def["toc_page_indices"], dpi=args.dpi)
        doc.close()

        for i, e in enumerate(entries, 1):
            sec = f"[{e['section']}] " if e.get('section') else ""
            auth = f"{e['author']} — " if e.get('author') else ""
            pg = f" (p.{e['page_start']})" if e.get('page_start') else " (NO PAGE)"
            print(f"  {i:3d}. {sec}{auth}{e['title'][:70]}{pg}")
    else:
        process_all(Path(args.series2_dir), Path(args.output_dir), dpi=args.dpi)
