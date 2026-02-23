"""Table of Contents parser for academic journal issues."""

from __future__ import annotations

import re

from .text_cleanup import clean_line, is_upperish, normalize_person_line, normalized_letters

END_MARKERS = ("contents", "sommario", "sommaire", "inhalt")


def extract_review_author_from_title(title: str) -> str:
    """Extract reviewer name from final parenthesized expression."""
    match = re.search(r"\(([^()]{3,120})\)\s*$", title or "")
    if not match:
        return ""
    candidate = normalize_person_line(match.group(1).strip())
    if len(candidate.split()) < 2:
        return ""
    return candidate


def _looks_like_section_header(line: str) -> bool:
    if not line:
        return False

    # Roman numeral section header: "III. NOTE DE LECTURĂ"
    roman = re.match(r"^([IVXLCM]+)\.?\s+(.+)$", line)
    if roman:
        return True

    # Standalone uppercase headings with no page suffix/digits.
    if any(ch.isdigit() for ch in line):
        return False
    words = line.split()
    if len(words) < 2:
        single_word_sections = {"recenzii", "reviews", "restituiri", "cuprins"}
        if line.lower().strip() not in single_word_sections:
            return False

    norm = normalized_letters(line)
    if norm in {"cuprins", "contents", "sommario", "inhalt"}:
        return False

    # Mixed-case but canonical section words.
    section_words = (
        "recenzii",
        "book reviews",
        "note de lectura",
        "studii si cercetari",
        "arhiva de folclor a academiei romane",
        "research and studies",
        "the folklore archive of the romanian academy",
        "restituiri",
    )
    lower = line.lower()
    if any(word in lower for word in section_words):
        return True

    # Avoid classifying author names (1-4 words) as sections.
    if is_upperish(line):
        if len(words) >= 5:
            return True
        section_connectors = {"DE", "SI", "ȘI", "A", "OF", "THE", "AND", "N", "O", "T", "E", "S"}
        cleaned_words = [re.sub(r"[^A-ZĂÂÎȘȚ]", "", word.upper()) for word in words]
        if any(word in section_connectors for word in cleaned_words):
            return True

    return False


def _looks_like_author_candidate(line: str) -> bool:
    line = clean_line(line)
    if not line or ":" in line:
        return False
    if any(ch.isdigit() for ch in line):
        return False
    if len(line) < 3 or len(line) > 140:
        return False

    words = [w for w in line.split() if re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", w)]
    if not (1 <= len(words) <= 4):
        return False

    # Avoid matching obvious section labels as authors.
    norm = normalized_letters(line)
    if any(tok in norm for tok in ("recenzii", "studii", "cercetari", "arhiva", "cuprins")):
        return False

    # Avoid punctuation-heavy lines (likely titles).
    if re.search(r"[.,;:!?\"“”]", line):
        return False
    connectors = {"de", "si", "și", "a", "of", "and", "the"}
    if any(word.lower().strip("-") in connectors for word in words):
        return False

    # Author lines are expected uppercase in current journal TOC layout.
    return is_upperish(line)


def _is_page_terminating_line(line: str) -> tuple[str, int] | None:
    m = re.match(r"^(.*?)(\d{1,4})\s*$", line)
    if not m:
        return None

    title = clean_line(m.group(1))
    return title, int(m.group(2))


def parse_toc_entries(toc_text: str) -> list[dict]:
    """Parse TOC block between CUPRINS and CONTENTS/SOMMARIO/INHALT markers."""
    lines = [clean_line(line) for line in toc_text.splitlines()]
    lines = [line for line in lines if line]

    start_idx = next((i for i, line in enumerate(lines) if "cuprins" in normalized_letters(line)), None)
    if start_idx is None:
        return []

    end_idx = next(
        (
            i
            for i, line in enumerate(lines[start_idx + 1 :], start_idx + 1)
            if any(marker in normalized_letters(line) for marker in END_MARKERS)
        ),
        len(lines),
    )

    toc_lines = lines[start_idx + 1 : end_idx]
    entries: list[dict] = []

    current_section = ""
    current_author = ""
    pending_title_parts: list[str] = []

    for line in toc_lines:
        # Section header handling.
        if _looks_like_section_header(line):
            roman_match = re.match(r"^([IVXLCM]+)\.?\s+(.+)$", line)
            current_section = clean_line(roman_match.group(2) if roman_match else line)
            current_author = ""
            pending_title_parts = []
            continue

        page_line = _is_page_terminating_line(line)
        if page_line:
            title, page = page_line
            if pending_title_parts:
                title = clean_line(" ".join(pending_title_parts + [title]))
                pending_title_parts = []
            elif not title:
                continue

            # Accept short but meaningful titles (e.g., "Prefață").
            if len(title) >= 3 and not title.isdigit():
                author_value = current_author
                section_norm = normalized_letters(current_section)
                if any(token in section_norm for token in ("recenzii", "bookreviews", "bookreview")):
                    review_author = extract_review_author_from_title(title)
                    if review_author:
                        author_value = review_author

                entries.append(
                    {
                        "author": author_value,
                        "title": title,
                        "start_page": page,
                        "section": current_section,
                    }
                )
            continue

        if _looks_like_author_candidate(line):
            # Treat as author only if line is compact enough.
            if len(line.split()) <= 4:
                current_author = normalize_person_line(line)
                pending_title_parts = []
                continue

        # Multi-line title continuation.
        pending_title_parts.append(line)

    deduped: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for entry in entries:
        key = (entry["start_page"], entry["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    deduped.sort(key=lambda item: item["start_page"])
    return deduped


def is_review_entry(entry: dict) -> bool:
    """Infer review entry from section and citation-like title style."""
    section_norm = normalized_letters(entry.get("section", ""))
    title_norm = normalized_letters(entry.get("title", ""))

    if any(tok in section_norm for tok in ("recenzii", "bookreviews", "bookreview")):
        return True

    title = entry.get("title", "")
    if title.count(",") >= 2 and re.search(r"\([^)]{3,80}\)\s*$", title):
        review_markers = ("editura", "press", "volume", "isbn", "vienna", "bucuresti", "clujnapoca")
        if any(tok in title_norm for tok in review_markers):
            return True

    return False
