"""Ingest helpers for AAF first series (1932-1945 BCU scans).

This module is intentionally separate from the modern ingest pipeline.
It handles OCR-heavy legacy issues where abstracts live in a final
"Résumé des articles" section.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # type: ignore

from .pdf_extract import extraction_is_weak, ocr_extract_text_range
from .text_cleanup import clean_line, normalize_person_line, normalize_text, normalized_letters, slugify

LOGGER = logging.getLogger(__name__)

_UPPER_ALPHA = "A-ZĂÂÎȘȚŞŢÉÈÊËÀÂÎÏÔÙÛÜÇ"
_LOWER_ALPHA = "a-zăâîșțşţéèêëàâîïôùûüç"
_ALPHA = f"{_UPPER_ALPHA}{_LOWER_ALPHA}"

_SPACED_UPPER_RE = re.compile(rf"\b(?:[{_UPPER_ALPHA}]\s+){{2,}}[{_UPPER_ALPHA}]\b")
_PAGE_TOKEN_TAIL_RE = re.compile(
    r"(?P<body>.*?\S)[\s\.,;:!?\^*'\"`<>/\\\-]+(?P<page>\d(?:\s*\d){0,3})\s*$"
)
_SUMMARY_ENTRY_RE = re.compile(
    rf"(?P<author>[{_UPPER_ALPHA}][{_UPPER_ALPHA}\s\.\-]{{2,}}[{_UPPER_ALPHA}])\s*,\s*"
    rf"(?P<title>.+?)"
    rf"\(\s*(?:[Pp]{{1,2}}\s*\.?\s*)?(?P<start>[A-Za-z\d\s]+)\s*[—\-]\s*(?P<end>[A-Za-z\d\s]+)\s*\)\.?",
    flags=re.DOTALL,
)

_SECTION_HEADER_KEYS = {"articole", "marunte", "studii", "cercetari", "recenzii", "cuprins", "contents"}


ROMAN_MAP = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
    7: "VII",
}


FRENCH_STOPWORDS = {
    "dans",
    "avec",
    "sans",
    "pour",
    "plus",
    "moins",
    "entre",
    "chez",
    "dont",
    "leur",
    "leurs",
    "elle",
    "elles",
    "nous",
    "vous",
    "ainsi",
    "comme",
    "mais",
    "aussi",
    "cette",
    "celui",
    "celle",
    "ceux",
    "celles",
    "sont",
    "etre",
    "etait",
    "avait",
    "apres",
    "avant",
    "toute",
    "toutes",
    "tous",
    "tout",
    "selon",
    "leurs",
    "fait",
    "faits",
    "faite",
    "faire",
    "dans",
    "dune",
    "dans",
    "sous",
    "dans",
    "leur",
    "deux",
    "trois",
    "quatre",
    "cinq",
    "cette",
    "celui",
    "ceci",
    "cela",
    "vers",
    "etre",
    "lors",
    "chez",
    "leurs",
    "leurs",
    "leurs",
    "article",
    "articles",
    "resume",
    "resumes",
    "folklore",
    "roumain",
    "roumaine",
    "roumains",
    "roumaines",
    "auteur",
    "auteurs",
    "archive",
    "academie",
    "roman",
    "romane",
    "pages",
    "page",
    "partie",
}


FR_TO_RO_KEYWORDS = {
    "folklore": "folclor",
    "roumain": "românesc",
    "roumaine": "românească",
    "roumains": "români",
    "roumaines": "române",
    "chanson": "cântec",
    "chansons": "cântece",
    "conte": "poveste",
    "contes": "povești",
    "legende": "legendă",
    "legendes": "legende",
    "tradition": "tradiție",
    "traditions": "tradiții",
    "coutume": "obicei",
    "coutumes": "obiceiuri",
    "bibliographie": "bibliografie",
    "etude": "studiu",
    "etudes": "studii",
    "recherche": "cercetare",
    "recherches": "cercetări",
    "village": "sat",
    "villages": "sate",
    "paysan": "țăran",
    "paysans": "țărani",
    "magique": "magic",
    "magiques": "magice",
    "poesie": "poezie",
    "poesies": "poezii",
    "litterature": "literatură",
    "region": "regiune",
    "regions": "regiuni",
    "langue": "limbă",
    "dialecte": "dialect",
    "dialectes": "dialecte",
    "musique": "muzică",
    "danse": "dans",
    "croyance": "credință",
    "croyances": "credințe",
    "rituel": "ritual",
    "rituels": "ritualuri",
    "histoire": "istorie",
    "memoire": "memorie",
    "manuscrit": "manuscris",
    "manuscrits": "manuscrise",
    "populaire": "popular",
    "populaires": "populare",
    "pastorel": "pastoral",
    "pastorale": "pastorală",
    "berger": "păstor",
    "bergers": "păstori",
    "femme": "femeie",
    "femmes": "femei",
}


SUPPLEMENT_MARKERS = (
    "bibliografia",
    "bibliographie",
    "raport",
    "rapport",
    "résumé",
    "resume",
    "table des planches",
    "table",
)


@dataclass
class TocEntry:
    index: int
    section: str
    author: str
    title: str
    page_start_label: str
    page_start: int | None
    page_end: int | None


@dataclass
class SummaryEntry:
    author: str
    title_fr: str
    page_start: int | None
    page_end: int | None
    abstract_fr: str
    source_start_page_pdf: int


def _collapse_spaced_upper(text: str) -> str:
    def _join(match: re.Match[str]) -> str:
        return match.group(0).replace(" ", "")

    return _SPACED_UPPER_RE.sub(_join, text)


def _normalize_ocr_line(line: str) -> str:
    line = clean_line(line)
    line = line.replace("\xad", "")
    line = line.replace("•", " ")
    line = line.replace(" . . . ", " ")
    line = line.replace("...", " ")
    line = _collapse_spaced_upper(line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _has_spaced_letter_noise(text: str) -> bool:
    tokens = re.findall(rf"[{_ALPHA}]+", text)
    if len(tokens) < 40:
        return False

    single_alpha = sum(1 for token in tokens if len(token) == 1)
    ratio = single_alpha / max(1, len(tokens))
    if ratio >= 0.34:
        return True

    return bool(re.search(rf"(?:\b[{_ALPHA}]\b\s+){{10,}}\b[{_ALPHA}]\b", text))


def _roman_to_int(token: str) -> int | None:
    token = token.strip().upper()
    if not token or not re.fullmatch(r"[IVXLCDM]+", token):
        return None

    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(token):
        value = values[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total if total > 0 else None


def _parse_page_label(label: str) -> int | None:
    raw = (label or "").strip().upper()
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        return None

    # Keep canonical roman numerals for front matter.
    if re.fullmatch(r"[IVXLCDM]+", raw):
        return _roman_to_int(raw)

    # OCR substitutions for numeric labels.
    transl_table = str.maketrans(
        {
            "O": "0",
            "Q": "9",
            "S": "5",
            "B": "8",
            "Z": "2",
            "Y": "7",
            "J": "1",
            "I": "1",
            "L": "1",
            "T": "1",
        }
    )
    normalized = raw.translate(transl_table)
    digits = re.sub(r"[^0-9]", "", normalized)
    if digits:
        return int(digits)

    roman = re.sub(r"[^IVXLCDM]", "", raw)
    if roman:
        return _roman_to_int(roman)
    return None


def _extract_tail_page(text: str) -> tuple[str, str] | None:
    stripped = re.sub(r"[\s\.\,\;\:\!\?\^\*'\"`<>/\\\-]+$", "", text.strip())
    match = _PAGE_TOKEN_TAIL_RE.match(stripped)
    if not match:
        return None

    body = match.group("body").strip(" .,-;:/")
    page = match.group("page").strip().upper()
    if not body:
        return None
    return body, page


def _split_author_title(raw: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", " ", raw.strip())
    raw = raw.replace("„", "\"").replace("”", "\"")
    if "," in raw:
        author_raw, title = raw.split(",", 1)
    else:
        tokens = raw.split()
        split_at = 0
        for idx, token in enumerate(tokens):
            if re.search(rf"[{_LOWER_ALPHA}]", token):
                split_at = idx
                break
        if 0 < split_at < len(tokens):
            author_raw = " ".join(tokens[:split_at])
            title = " ".join(tokens[split_at:])
        else:
            author_raw = ""
            title = raw

    author_raw = _collapse_spaced_upper(author_raw)
    author = normalize_person_line(author_raw) if author_raw else ""
    title = re.sub(r"\s+", " ", title).strip(" .-")
    return author, title


def _looks_like_toc_entry_start(line: str) -> bool:
    if "," not in line:
        return False
    head, tail = line.split(",", 1)
    head = _collapse_spaced_upper(head).strip(" .-")
    tail = tail.strip()
    if len(head) < 3 or len(tail) < 4:
        return False
    if re.search(rf"[{_LOWER_ALPHA}]", head):
        return False
    if not re.search(rf"[{_UPPER_ALPHA}]", head):
        return False
    return bool(re.search(rf"[{_LOWER_ALPHA}]", tail))


def _is_author_fragment(text: str) -> bool:
    probe = _collapse_spaced_upper(text).strip(" .,-;:/")
    if not probe or "," in probe:
        return False
    if re.search(rf"[{_LOWER_ALPHA}]", probe):
        return False
    words = [word for word in re.split(r"\s+", probe) if word]
    if not words or len(words) > 4:
        return False
    return True


def _is_section_header(line: str) -> bool:
    if "," in line:
        return False
    if _extract_tail_page(line):
        return False
    norm = normalized_letters(line)
    if not norm:
        return False
    if norm in _SECTION_HEADER_KEYS:
        return True
    if any(norm.startswith(f"{key} ") for key in _SECTION_HEADER_KEYS):
        return True
    return bool(re.match(rf"^[IVXLCDM]+\s+[{_UPPER_ALPHA}\s]+$", line.strip()))


def _is_toc_header(line: str) -> bool:
    norm = normalized_letters(line)
    if not norm:
        return False
    if norm.startswith("cuprins"):
        return True
    if norm in {"pag", "pagi"}:
        return True
    return False


def _extract_page_only_token(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None

    if re.search(r"\d{3,4}\s*[—\-]\s*\d{2,4}", raw):
        # Avoid taking years/ranges as page markers.
        return None

    if re.search(rf"[{_ALPHA}]", raw):
        # Keep OCR noise tolerant for lines like "5 s", "101 <s", but reject
        # true text lines.
        letters = re.findall(rf"[{_ALPHA}]", raw)
        if len(letters) > 1:
            romanish = "".join(letters).upper()
            if not re.fullmatch(r"[IVXLCDM]+", romanish):
                return None
            if not re.fullmatch(rf"[\s\.\,\;\:\!\?\^\*'\"`<>/\-IVXLCDM]+", raw, re.IGNORECASE):
                return None

    digits = re.findall(r"\d", raw)
    if digits:
        compact_digits = "".join(digits)
        if len(compact_digits) > 3:
            return None
        # Accept only if line does not look like prose.
        words = re.findall(rf"[{_ALPHA}]{{2,}}", raw)
        if not words:
            return str(int(compact_digits))
        if len(words) == 1 and words[0].lower() in {"s"}:
            return str(int(compact_digits))

    roman = re.sub(r"[^IVXLCDM]", "", raw.upper())
    if roman and re.fullmatch(r"[IVXLCDM]{1,5}", roman):
        return roman
    return None


def _read_page_text_ocr_aware(pdf_path: Path, page_no: int) -> tuple[str, str]:
    with fitz.open(pdf_path) as doc:
        if page_no < 1 or page_no > len(doc):
            return "", "fitz"
        text = doc[page_no - 1].get_text("text") or ""

    fitz_is_noisy = _has_spaced_letter_noise(text)
    if not extraction_is_weak(text, min_chars=120, min_words=20) and not fitz_is_noisy:
        return text, "fitz"

    ocr = ocr_extract_text_range(pdf_path, page_no, page_no, temp_stem=f"{pdf_path.stem}-p{page_no:03d}")
    if ocr:
        ocr_is_noisy = _has_spaced_letter_noise(ocr)
        if not extraction_is_weak(ocr, min_chars=80, min_words=12):
            return ocr, "ocr"
        if fitz_is_noisy and not ocr_is_noisy:
            return ocr, "ocr"
    return text, "fitz"


def _read_page_text_toc_aware(pdf_path: Path, page_no: int) -> tuple[str, str]:
    with fitz.open(pdf_path) as doc:
        if page_no < 1 or page_no > len(doc):
            return "", "fitz"
        text = doc[page_no - 1].get_text("text") or ""

    if not extraction_is_weak(text, min_chars=80, min_words=10):
        return text, "fitz"

    ocr = ocr_extract_text_range(pdf_path, page_no, page_no, temp_stem=f"{pdf_path.stem}-toc-p{page_no:03d}")
    if ocr and not extraction_is_weak(ocr, min_chars=60, min_words=8):
        return ocr, "ocr"
    return text, "fitz"


def find_toc_page(pdf_path: Path, search_pages: int = 14) -> tuple[int, str]:
    with fitz.open(pdf_path) as doc:
        total = len(doc)
    limit = min(total, search_pages)
    best = (0, "")
    for page_no in range(1, limit + 1):
        text, source = _read_page_text_toc_aware(pdf_path, page_no)
        normalized = normalized_letters(_collapse_spaced_upper(text))
        if "cuprins" in normalized:
            LOGGER.debug("TOC page found in %s at p%s via %s", pdf_path.name, page_no, source)
            return page_no, text
        if "contents" in normalized and not best[0]:
            best = (page_no, text)
    if best[0]:
        return best
    raise RuntimeError(f"Cannot locate TOC page in {pdf_path}")


def parse_toc_entries(toc_text: str) -> list[TocEntry]:
    lines = [_normalize_ocr_line(line) for line in toc_text.splitlines()]
    lines = [line for line in lines if line]

    entries: list[TocEntry] = []
    section = ""
    section_pending = ""
    current = ""

    def _finalize_current(page_label: str = "") -> None:
        nonlocal current
        candidate = re.sub(r"\s+", " ", current).strip(" .,-;:/")
        current = ""
        if not candidate:
            return
        if _is_author_fragment(candidate):
            return
        author, title = _split_author_title(candidate)
        if not title:
            return
        if not author and not re.search(rf"[{_LOWER_ALPHA}]", title) and len(title.split()) <= 4:
            return
        title_norm = normalize_text(title)
        if "resume des articles" in title_norm or "table des planches" in title_norm:
            return
        entries.append(
            TocEntry(
                index=len(entries) + 1,
                section=section,
                author=author,
                title=title,
                page_start_label=page_label,
                page_start=_parse_page_label(page_label) if page_label else None,
                page_end=None,
            )
        )

    for idx, raw in enumerate(lines):
        line = raw.strip()
        next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        if _is_toc_header(line):
            continue

        page_only = _extract_page_only_token(line)
        if page_only and current:
            next_page_only = _extract_page_only_token(next_line) if next_line else None
            if (
                page_only in {"I", "V"}
                and next_page_only
                and next_page_only.isdigit()
                and int(next_page_only) >= 10
            ):
                # OCR noise case: "... Geneza i" followed by real page on next line.
                continue
            _finalize_current(page_only)
            continue
        if page_only and not current:
            continue

        if _is_section_header(line):
            if section_pending:
                section = f"{section_pending} {line}".strip()
                section_pending = ""
            elif len(line.split()) == 1:
                section_pending = line
            else:
                section = line
            continue
        if section_pending:
            section = section_pending
            section_pending = ""

        if line in {".", "..", "...", ";", ":", "-", "—"}:
            continue

        if current and _looks_like_toc_entry_start(line) and not _extract_tail_page(current):
            if _is_author_fragment(current):
                current = f"{current} {line}".strip()
            else:
                _finalize_current("")
                current = line
        elif current:
            current = f"{current} {line}".strip()
        else:
            current = line

        parsed_tail = _extract_tail_page(current)
        if parsed_tail:
            body, page_label = parsed_tail
            page_num = _parse_page_label(page_label)
            if page_num is not None and page_num <= 600:
                current = body
                _finalize_current(page_label)

    if current:
        # Best effort salvage in case final page marker is missing.
        parsed = _extract_tail_page(current)
        if parsed:
            body, page_label = parsed
            page_num = _parse_page_label(page_label)
            if page_num is not None and page_num <= 600:
                current = body
                _finalize_current(page_label)
            else:
                _finalize_current("")
        else:
            _finalize_current("")

    # Re-index before post-processing.
    for idx, entry in enumerate(entries, start=1):
        entry.index = idx

    # Repair OCR page anomalies (e.g. "III" as 111, year lines misread as pages).
    for idx, entry in enumerate(entries):
        label_clean = re.sub(r"[^0-9IVXLCDM]", "", (entry.page_start_label or "").upper())
        prev_numeric = next(
            (entries[j].page_start for j in range(idx - 1, -1, -1) if entries[j].page_start is not None),
            None,
        )
        next_numeric = next(
            (entries[j].page_start for j in range(idx + 1, len(entries)) if entries[j].page_start is not None),
            None,
        )
        if entry.page_start is None or prev_numeric is None:
            continue
        if entry.page_start >= prev_numeric:
            continue

        if label_clean and set(label_clean) == {"I"} and len(label_clean) >= 2:
            candidate = int("1" * len(label_clean))
            if candidate > prev_numeric and (next_numeric is None or candidate < next_numeric):
                entry.page_start = candidate
                continue

        # Most likely OCR captured a year instead of page.
        entry.page_start = None

    # Compute page_end from next numeric page start.
    for entry in entries:
        entry.page_end = None

    numeric_indexes = [i for i, entry in enumerate(entries) if entry.page_start is not None]
    for idx in numeric_indexes:
        cur = entries[idx]
        next_numeric = next((entries[j] for j in numeric_indexes if j > idx), None)
        if cur.page_start is None:
            continue
        if next_numeric and next_numeric.page_start is not None and next_numeric.page_start > cur.page_start:
            cur.page_end = next_numeric.page_start - 1

    for idx, entry in enumerate(entries, start=1):
        entry.index = idx

    return entries


def _summary_heading_present(text: str) -> bool:
    norm = normalized_letters(_collapse_spaced_upper(text))
    return "resumedesarticles" in norm or "resumedesarticles" in norm


def find_summary_start_page(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        total = len(doc)
        start_scan = max(1, int(total * 0.60))
        for page_no in range(start_scan, total + 1):
            text = doc[page_no - 1].get_text("text") or ""
            if _summary_heading_present(text):
                return page_no
    raise RuntimeError(f"Cannot locate Résumé des articles in {pdf_path}")


def extract_summary_text(pdf_path: Path, start_page: int) -> str:
    chunks: list[str] = []
    with fitz.open(pdf_path) as doc:
        total = len(doc)
        for page_no in range(start_page, total + 1):
            text, _source = _read_page_text_ocr_aware(pdf_path, page_no)
            if text:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def parse_summary_entries(summary_text: str, summary_start_page_pdf: int) -> list[SummaryEntry]:
    text = summary_text.replace("\xad", "")
    text = _collapse_spaced_upper(text)
    text = re.sub(r"[_~`´^]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Normalize compact page ranges like "(pp. 3341)" => "(p. 33—41)".
    text = re.sub(
        r"\(\s*pp?\.?\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*\)",
        r"(p. \1\2—\3\4)",
        text,
        flags=re.IGNORECASE,
    )

    # Some scans delimit the author with "." instead of ",".
    text = re.sub(
        rf"(?P<author>[{_UPPER_ALPHA}][{_UPPER_ALPHA}\s\.\-]{{2,}}[{_UPPER_ALPHA}])\.\s+"
        rf"(?=(?:[^()]){{5,140}}\(\s*(?:[Pp]{{1,2}}\s*\.?\s*)?[A-Za-z\d\s]+(?:[—\-])[A-Za-z\d\s]+\))",
        r"\g<author>, ",
        text,
    )

    # Drop repeated heading noise inside pages.
    text = re.sub(r"\b\d+\s*R[ÉE]SUM[ÉE]\s+DES\s+ARTICLES\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"R[ÉE]SUM[ÉE]\s+DES\s+ARTICLES", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(rf"^[^{_UPPER_ALPHA}]+", "", text)
    text = re.sub(r"^ST\s+ID\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        rf"^(?P<author>[{_UPPER_ALPHA}{_LOWER_ALPHA}\.\-\s]{{3,80}}?),",
        lambda m: f"{m.group('author').upper()},",
        text,
        count=1,
    )

    matches = list(_SUMMARY_ENTRY_RE.finditer(text))
    results: list[SummaryEntry] = []
    for i, match in enumerate(matches):
        author_raw = _collapse_spaced_upper(match.group("author")).strip(" .,-;:")
        if not author_raw:
            continue
        author_letters = re.sub(rf"[^{_UPPER_ALPHA}]", "", author_raw.upper())
        if author_letters and re.fullmatch(r"[IVXLCDM]{1,4}", author_letters):
            continue

        title_fr = re.sub(r"\s+", " ", match.group("title")).strip(" .,-;:")
        start = _parse_page_label(match.group("start"))
        end = _parse_page_label(match.group("end"))

        if not title_fr:
            continue

        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        abstract = text[match.end() : next_start]
        abstract = re.sub(r"\b\d+\s*R[ÉE]SUM[ÉE]\s+DES\s+ARTICLES\b", " ", abstract, flags=re.IGNORECASE)
        abstract = re.sub(r"\s+", " ", abstract).strip(" .,-;:")
        if abstract and abstract[-1] not in ".!?":
            abstract = f"{abstract}."

        results.append(
            SummaryEntry(
                author=normalize_person_line(author_raw),
                title_fr=title_fr,
                page_start=start,
                page_end=end,
                abstract_fr=abstract,
                source_start_page_pdf=summary_start_page_pdf,
            )
        )
    return results


def _is_supplement_title(title: str) -> bool:
    norm = normalize_text(title)
    return any(marker in norm for marker in SUPPLEMENT_MARKERS)


def _summary_match_score(entry: TocEntry, summary: SummaryEntry) -> tuple[int, int, int]:
    page_score = 0
    if entry.page_start is not None and summary.page_start is not None:
        if entry.page_start == summary.page_start:
            page_score += 5
        elif abs(entry.page_start - summary.page_start) <= 1:
            page_score += 2
    if entry.page_end is not None and summary.page_end is not None:
        if entry.page_end == summary.page_end:
            page_score += 4
        elif abs(entry.page_end - summary.page_end) <= 2:
            page_score += 1

    author_entry = normalize_text(entry.author)
    author_summary = normalize_text(summary.author)
    author_score = 0
    if author_entry and author_summary:
        if author_entry == author_summary:
            author_score = 4
        elif all(part in author_summary for part in author_entry.split()[:2]):
            author_score = 2

    title_entry = normalize_text(entry.title)
    title_summary = normalize_text(summary.title_fr)
    overlap = len(set(title_entry.split()) & set(title_summary.split()))
    return (page_score, author_score, overlap)


def match_toc_with_summaries(entries: list[TocEntry], summaries: list[SummaryEntry]) -> dict[int, SummaryEntry]:
    matches: dict[int, SummaryEntry] = {}
    used_summary_indexes: set[int] = set()

    for entry in entries:
        if _is_supplement_title(entry.title):
            continue

        candidates: list[tuple[tuple[int, int, int], int, SummaryEntry]] = []
        for idx, summary in enumerate(summaries):
            if idx in used_summary_indexes:
                continue
            score = _summary_match_score(entry, summary)
            if score[0] <= 0 and score[1] <= 0 and score[2] <= 0:
                continue
            candidates.append((score, idx, summary))

        if not candidates:
            continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_idx, best_summary = candidates[0]
        if best_score[0] <= 0 and best_score[1] <= 0:
            # Keep fuzzy title-only matches conservative.
            continue
        matches[entry.index] = best_summary
        used_summary_indexes.add(best_idx)

    return matches


def extract_keywords_fr(text: str, size: int = 5) -> list[str]:
    tokens = re.findall(rf"[{_ALPHA}]{{4,}}", (text or "").lower())
    filtered = []
    for token in tokens:
        norm = normalized_letters(token)
        if not norm or norm in FRENCH_STOPWORDS:
            continue
        if norm.isdigit():
            continue
        filtered.append(token)

    if not filtered:
        return []

    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for token in filtered:
        key = normalize_text(token)
        if key not in counts:
            counts[key] = 0
            first_seen[key] = len(first_seen)
        counts[key] += 1

    ordered = sorted(counts.keys(), key=lambda key: (-counts[key], first_seen[key]))
    selected = [key for key in ordered[:size]]
    return selected


def translate_keywords_to_ro(keywords_fr: Iterable[str]) -> list[str]:
    translated: list[str] = []
    seen: set[str] = set()
    for keyword in keywords_fr:
        key = normalize_text(keyword)
        translated_word = FR_TO_RO_KEYWORDS.get(key, keyword)
        cleaned = re.sub(r"\s+", " ", translated_word).strip()
        if not cleaned:
            continue
        cleaned_key = normalize_text(cleaned)
        if cleaned_key in seen:
            continue
        seen.add(cleaned_key)
        translated.append(cleaned)
    return translated


def issue_slug_from_pdf(pdf_path: Path) -> str:
    match = re.search(r"_(\d{4})_(\d{3})\.pdf$", pdf_path.name, re.IGNORECASE)
    if not match:
        return slugify(pdf_path.stem)
    year = match.group(1)
    index = int(match.group(2))
    roman = ROMAN_MAP.get(index, str(index))
    return f"aaf-seria1-{year}-vol-{slugify(roman)}"


def issue_meta_from_pdf(pdf_path: Path) -> dict:
    match = re.search(r"_(\d{4})_(\d{3})\.pdf$", pdf_path.name, re.IGNORECASE)
    year = match.group(1) if match else ""
    index = int(match.group(2)) if match else 0
    roman = ROMAN_MAP.get(index, str(index) if index else "")
    return {
        "slug": issue_slug_from_pdf(pdf_path),
        "series": "seria-1",
        "series_label": "Seria I (1932-1945)",
        "year": year,
        "volume": roman,
        "number": str(index) if index else "",
        "title": f"Anuarul Arhivei de Folklor {roman}".strip(),
        "source_pdf_name": pdf_path.name,
    }


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _to_int(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _ocr_normalize(text: str) -> str:
    """Aggressively normalize text for OCR-tolerant comparison."""
    text = normalize_text(text)
    # Collapse spaced-out letters like "P R E F A Ţ A" → "PREFAŢA".
    text = _collapse_spaced_upper(text)
    # Also collapse spaced lowercase single chars.
    text = re.sub(r"(?<=\b[a-zăâîșțşţ])\s+(?=[a-zăâîșțşţ]\b)", "", text)
    # Remove common OCR artifacts.
    text = re.sub(r"[\^\*]", "", text)
    # Normalize Romanian diacritics variants: ş→s, ţ→t, ă→a, â→a, î→i.
    for old, new in [("ş", "s"), ("ţ", "t"), ("ă", "a"), ("â", "a"), ("î", "i"),
                     ("ș", "s"), ("ț", "t"), ("é", "e"), ("è", "e"), ("ê", "e"),
                     ("ë", "e"), ("à", "a"), ("ü", "u"), ("ö", "o"), ("ä", "a")]:
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_article_pdf_page(
    doc: fitz.Document,
    title: str,
    toc_page: int | None,
    base_offset: int,
    search_margin: int = 6,
    skip_pages: frozenset[int] | None = None,
) -> int | None:
    """Search for an article title in the PDF and return its 1-based PDF page number.

    skip_pages: set of 0-indexed page numbers to exclude (e.g. TOC page).
    """
    if not title or len(title) < 4:
        return None

    _skip = skip_pages or frozenset()

    needle = _ocr_normalize(title)[:80]
    needle_words = [w for w in needle.split() if len(w) > 2][:6]
    if not needle_words:
        return None

    total = len(doc)
    if toc_page is not None:
        center = toc_page + base_offset - 1  # 0-indexed estimate
        search_start = max(0, center - search_margin)
        search_end = min(total, center + search_margin + 1)
    else:
        search_start = 0
        search_end = total

    for page_idx in range(search_start, search_end):
        if page_idx in _skip:
            continue
        page_text = doc[page_idx].get_text("text") or ""
        text_norm = _ocr_normalize(page_text)
        if not text_norm:
            continue

        # Full title match -- verify it's near the top of the page.
        if needle in text_norm:
            first_portion = _ocr_normalize(page_text[:800])
            if needle[:20] in first_portion:
                return page_idx + 1  # 1-based

        # Check first ~400 chars of page for title words (article start, not mid-text).
        first_block = _ocr_normalize(page_text[:500])
        overlap = sum(1 for w in needle_words if w in first_block)
        required = max(2, min(3, len(needle_words) - 1))
        if overlap >= required:
            return page_idx + 1

    return None


def infer_cover_offset(pdf_path: Path, toc_entries: list[TocEntry], toc_page_pdf: int) -> int:
    """Detect initial cover offset from the first locatable TOC entry."""
    anchor_entry: TocEntry | None = None
    for entry in toc_entries:
        if entry.page_start is not None and len(entry.title) >= 6:
            anchor_entry = entry
            break

    if anchor_entry is None:
        LOGGER.warning("infer_cover_offset: no usable anchor entry in %s, defaulting to 0", pdf_path.name)
        return 0

    with fitz.open(pdf_path) as doc:
        # Skip all pages up to and including the TOC page to avoid matching on the TOC itself.
        skip = frozenset(range(toc_page_pdf))
        found = _find_article_pdf_page(doc, anchor_entry.title, anchor_entry.page_start, base_offset=0, search_margin=10, skip_pages=skip)
        if found:
            offset = found - anchor_entry.page_start
            LOGGER.info(
                "infer_cover_offset %s: '%s' at PDF page %d, TOC %s -> offset=%d",
                pdf_path.name, anchor_entry.title[:40], found, anchor_entry.page_start, offset,
            )
            return offset

    LOGGER.warning("infer_cover_offset: anchor title not found in %s, defaulting to 0", pdf_path.name)
    return 0


def locate_article_pages(
    pdf_path: Path,
    toc_entries: list[TocEntry],
    base_offset: int,
    toc_page_pdf: int = 0,
) -> dict[int, int]:
    """For each TOC entry, find the actual 1-based PDF page where the article starts.

    Returns: {toc_entry_index: pdf_page_1based}
    """
    result: dict[int, int] = {}
    # Skip all pages up to and including the TOC page to avoid false matches.
    skip_up_to = max(toc_page_pdf, base_offset) if toc_page_pdf > 0 else max(0, base_offset)
    skip = frozenset(range(skip_up_to))

    with fitz.open(pdf_path) as doc:
        for entry in toc_entries:
            found = _find_article_pdf_page(
                doc, entry.title, entry.page_start, base_offset, search_margin=15, skip_pages=skip,
            )
            if found:
                result[entry.index] = found
                LOGGER.debug(
                    "locate_article_pages: #%d '%s' -> PDF page %d",
                    entry.index, entry.title[:40], found,
                )
            else:
                # Fallback: use offset-based estimate.
                if entry.page_start is not None:
                    est = entry.page_start + base_offset
                    result[entry.index] = max(1, min(est, len(doc)))
                    LOGGER.warning(
                        "locate_article_pages: #%d '%s' NOT FOUND, using estimate PDF page %d",
                        entry.index, entry.title[:40], result[entry.index],
                    )
    return result


def _is_title_match(expected_title: str, page_text: str) -> bool:
    title_norm = _ocr_normalize(expected_title)
    text_norm = _ocr_normalize(page_text)
    if not title_norm or not text_norm:
        return False
    if title_norm in text_norm:
        return True

    words = [word for word in title_norm.split() if len(word) > 2]
    if len(words) >= 4:
        anchor = " ".join(words[:4])
        if anchor in text_norm:
            return True

    unique_words = list(dict.fromkeys(words))
    if not unique_words:
        return False

    # Stricter matching: require meaningful overlap, not just 1-2 words.
    overlap = sum(1 for token in unique_words if token in text_norm)
    if len(unique_words) <= 3:
        threshold = max(2, len(unique_words))
    elif len(unique_words) <= 6:
        threshold = 3
    else:
        threshold = 4
    return overlap >= threshold


def _extract_first_page_for_validation(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        if not len(doc):
            return ""
        text = doc[0].get_text("text") or ""

    if not extraction_is_weak(text, min_chars=80, min_words=10):
        return text

    ocr = ocr_extract_text_range(pdf_path, 1, 1, temp_stem=f"{pdf_path.stem}-verify-p001")
    return ocr or text


def _split_issue_articles(
    pdf_path: Path,
    issue_slug: str,
    issue_dir: Path,
    rows: list[dict],
    summary_start_pdf: int,
    cover_offset_pages: int = 0,
    located_pages: dict[int, int] | None = None,
) -> None:
    articles_dir = issue_dir / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(pdf_path) as source_doc:
        total_pages = len(source_doc)
        if total_pages < 1:
            return

        summary_cap = summary_start_pdf - 1 if summary_start_pdf > 1 else total_pages
        summary_cap = max(1, min(summary_cap, total_pages))
        toc_total_cap = max(1, total_pages - cover_offset_pages)
        toc_summary_cap = max(1, summary_cap - cover_offset_pages)
        start_candidates = [
            _to_int(row.get("pages_start")) or _to_int(row.get("summary_pages_start"))
            for row in rows
        ]
        explicit_end_candidates = [
            _to_int(row.get("pages_end")) or _to_int(row.get("summary_pages_end"))
            for row in rows
        ]
        previous_end = 0

        _located = located_pages or {}

        for idx, row in enumerate(rows):
            start = start_candidates[idx]
            explicit_end = explicit_end_candidates[idx]
            toc_index = _to_int(row.get("toc_index")) or (idx + 1)

            if start is None and previous_end < toc_summary_cap:
                start = previous_end + 1
            if start is None:
                row["article_pdf_path"] = ""
                row["split_pages_start_pdf"] = ""
                row["split_pages_end_pdf"] = ""
                row["split_source_start_pdf"] = ""
                row["split_source_end_pdf"] = ""
                row["split_title_ok"] = "no"
                continue

            toc_start = max(1, min(start, toc_total_cap))

            # Use located PDF page if available; otherwise fall back to offset.
            if toc_index in _located:
                source_start = min(total_pages, _located[toc_index])
            else:
                source_start = min(total_pages, toc_start + cover_offset_pages)

            # Determine next article's actual PDF start for end-page calculation.
            next_source_start = None
            for future_idx in range(idx + 1, len(rows)):
                future_toc_index = _to_int(rows[future_idx].get("toc_index")) or (future_idx + 1)
                if future_toc_index in _located:
                    next_source_start = _located[future_toc_index]
                    break
                future_start = start_candidates[future_idx]
                if future_start is not None:
                    next_source_start = min(total_pages, future_start + cover_offset_pages)
                    break

            if next_source_start is not None:
                source_end = next_source_start - 1
            elif explicit_end is not None and explicit_end >= toc_start:
                source_end = min(total_pages, explicit_end + cover_offset_pages)
            else:
                source_end = min(total_pages, summary_cap)

            source_end = max(source_start, min(source_end, total_pages))

            # Derive toc-space page numbers for reporting.
            toc_end = max(toc_start, source_end - cover_offset_pages)

            slug = slugify(str(row.get("title") or ""))[:120] or f"article-{toc_index:03d}"
            filename = f"{toc_index:03d}-{slug}.pdf"
            out_pdf = articles_dir / filename

            article_doc = fitz.open()
            article_doc.insert_pdf(source_doc, from_page=source_start - 1, to_page=source_end - 1)
            article_doc.save(out_pdf, garbage=3, deflate=True)
            article_doc.close()

            first_page_text = _extract_first_page_for_validation(out_pdf)
            title_ok = _is_title_match(str(row.get("title") or ""), first_page_text)

            row["article_pdf_path"] = f"ingest/series1/issues/{issue_slug}/articles/{filename}"
            row["split_pages_start_pdf"] = toc_start
            row["split_pages_end_pdf"] = toc_end
            row["split_source_start_pdf"] = source_start
            row["split_source_end_pdf"] = source_end
            row["split_title_ok"] = "yes" if title_ok else "no"

            previous_end = max(previous_end, toc_end)

            if not title_ok:
                LOGGER.warning(
                    "Series1 split validation mismatch %s #%s | title_ok=%s | %s",
                    issue_slug,
                    toc_index,
                    title_ok,
                    row.get("title", ""),
                )


def process_issue(pdf_path: Path, out_root: Path, copy_source_pdf: bool = True) -> tuple[dict, list[dict]]:
    issue_meta = issue_meta_from_pdf(pdf_path)
    issue_dir = out_root / "issues" / issue_meta["slug"]
    meta_dir = issue_dir / "metadata"
    source_dir = issue_dir / "source"

    issue_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    if copy_source_pdf:
        shutil.copy2(pdf_path, source_dir / "issue.pdf")

    toc_page, toc_text = find_toc_page(pdf_path)
    toc_entries = parse_toc_entries(toc_text)
    if not toc_entries:
        raise RuntimeError(f"No TOC entries parsed for {pdf_path}")

    summary_start_pdf = find_summary_start_page(pdf_path)
    summary_text = extract_summary_text(pdf_path, summary_start_pdf)
    summary_entries = parse_summary_entries(summary_text, summary_start_pdf)
    summary_map = match_toc_with_summaries(toc_entries, summary_entries)

    rows: list[dict] = []
    for entry in toc_entries:
        summary = summary_map.get(entry.index)
        abstract_fr = summary.abstract_fr if summary else ""
        page_start = entry.page_start
        page_end = entry.page_end
        if summary:
            if page_start is None and summary.page_start is not None:
                page_start = summary.page_start
            if page_end is None and summary.page_end is not None:
                page_end = summary.page_end

        keywords_source = abstract_fr or (summary.title_fr if summary else entry.title)
        keywords_fr = extract_keywords_fr(keywords_source, size=5) if keywords_source else []
        if len(keywords_fr) < 5 and summary:
            extra = extract_keywords_fr(summary.title_fr, size=8)
            merged: list[str] = []
            seen: set[str] = set()
            for token in [*keywords_fr, *extra]:
                key = normalize_text(token)
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(token)
                if len(merged) == 5:
                    break
            keywords_fr = merged
        keywords_ro = translate_keywords_to_ro(keywords_fr) if keywords_fr else []

        rows.append(
            {
                "series": issue_meta["series_label"],
                "issue_slug": issue_meta["slug"],
                "year": issue_meta["year"],
                "volume": issue_meta["volume"],
                "issue_number": issue_meta["number"],
                "toc_index": entry.index,
                "section": entry.section,
                "author": entry.author,
                "title": entry.title,
                "pages_start_label": entry.page_start_label,
                "pages_start": page_start or "",
                "pages_end": page_end or "",
                "abstract_fr": abstract_fr,
                "keywords_fr": ", ".join(keywords_fr),
                "keywords_ro": ", ".join(keywords_ro),
                "summary_matched": "yes" if summary else "no",
                "summary_pages_start": summary.page_start if summary and summary.page_start else "",
                "summary_pages_end": summary.page_end if summary and summary.page_end else "",
                "source_pdf": str(pdf_path),
                "toc_page_pdf": toc_page,
                "summary_start_page_pdf": summary_start_pdf,
                "article_pdf_path": "",
                "split_pages_start_pdf": "",
                "split_pages_end_pdf": "",
                "split_source_start_pdf": "",
                "split_source_end_pdf": "",
                "split_title_ok": "",
            }
        )

    cover_offset = infer_cover_offset(pdf_path, toc_entries, toc_page)
    located = locate_article_pages(pdf_path, toc_entries, cover_offset, toc_page_pdf=toc_page)
    _split_issue_articles(
        pdf_path=pdf_path,
        issue_slug=issue_meta["slug"],
        issue_dir=issue_dir,
        rows=rows,
        summary_start_pdf=summary_start_pdf,
        cover_offset_pages=cover_offset,
        located_pages=located,
    )

    toc_payload = [
        {
            "index": e.index,
            "section": e.section,
            "author": e.author,
            "title": e.title,
            "page_start_label": e.page_start_label,
            "page_start": e.page_start,
            "page_end": e.page_end,
        }
        for e in toc_entries
    ]
    summary_payload = [
        {
            "author": e.author,
            "title_fr": e.title_fr,
            "page_start": e.page_start,
            "page_end": e.page_end,
            "abstract_fr": e.abstract_fr,
            "source_start_page_pdf": e.source_start_page_pdf,
        }
        for e in summary_entries
    ]

    write_json(meta_dir / "issue.json", issue_meta)
    write_json(meta_dir / "toc_entries.json", toc_payload)
    write_json(meta_dir / "summary_entries.json", summary_payload)
    write_json(meta_dir / "articles_with_resume.json", rows)
    write_csv(
        meta_dir / "articles_with_resume.csv",
        rows,
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
        "Series1 processed %s | toc=%s | summaries=%s | matched=%s",
        issue_meta["slug"],
        len(toc_entries),
        len(summary_entries),
        sum(1 for row in rows if row["summary_matched"] == "yes"),
    )
    return issue_meta, rows
