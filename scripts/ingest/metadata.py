"""Metadata extraction from article frontmatter."""

from __future__ import annotations

import re

from .language import detect_language
from .toc_parser import is_review_entry
from .text_cleanup import (
    clean_line,
    enforce_last_keyword_from_context,
    merge_keyword_fields,
    normalize_keywords,
    normalize_person_line,
    normalize_text,
    normalized_letters,
    sanitize_abstract_text,
    strip_noise_lines,
)

KEYWORD_LABELS = ("keywords", "keyword", "cuvintecheie", "schlusselworte", "motscles")


def line_matches_title(line: str, title: str) -> bool:
    line_n = re.sub(r"\s+", " ", line.lower()).strip()
    title_n = re.sub(r"\s+", " ", title.lower()).strip()
    if not line_n or not title_n:
        return False

    if line_n in title_n or title_n in line_n:
        return True

    title_tokens = [tok for tok in re.split(r"\W+", title_n) if tok]
    line_tokens = set(tok for tok in re.split(r"\W+", line_n) if tok)
    overlap = sum(1 for tok in title_tokens[:8] if tok in line_tokens)
    return overlap >= 3


def extract_doi_field(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"(?:https?://doi\.org/|doi\s*:?\s*)(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().rstrip(".,;)")


def extract_emails_field(text: str) -> str:
    if not text:
        return ""
    emails = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)

    seen: set[str] = set()
    deduped: list[str] = []
    for email in emails:
        lowered = email.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(email)
    return "; ".join(deduped)


def _collect_block(lines: list[str], start_idx: int, stop_terms: tuple[str, ...], max_lines: int, max_chars: int) -> str:
    buf: list[str] = []
    for idx in range(start_idx, min(len(lines), start_idx + max_lines)):
        line = clean_line(lines[idx])
        if not line:
            if buf:
                break
            continue

        norm = normalized_letters(line)
        if any(term in norm for term in stop_terms):
            break
        if re.match(r"^[\*\u2217]", line):
            break
        if norm.startswith("anuarularhiveidefolclor"):
            break

        buf.append(line)
        if sum(len(part) for part in buf) >= max_chars:
            break

    text = " ".join(buf)
    return re.sub(r"\s+", " ", text).strip()


def _extract_labeled_field(
    lines: list[str],
    labels: tuple[str, ...],
    stop_terms: tuple[str, ...],
    max_lines: int = 12,
    max_chars: int = 2500,
) -> str:
    for idx, line in enumerate(lines):
        norm = normalized_letters(line)
        if not any(label in norm for label in labels):
            continue

        value = ""
        if ":" in line:
            value = line.split(":", 1)[1].strip()
        elif " - " in line:
            value = line.split(" - ", 1)[1].strip()

        continuation = _collect_block(
            lines,
            idx + 1,
            stop_terms=stop_terms,
            max_lines=max_lines,
            max_chars=max_chars,
        )

        merged = f"{value} {continuation}".strip()
        merged = re.sub(r"\s+", " ", merged).strip(" ;,")
        return merged
    return ""


def _extract_keywords_field(lines: list[str], labels: tuple[str, ...]) -> str:
    stop_terms = (
        "keywords",
        "keyword",
        "cuvintecheie",
        "rezumat",
        "abstract",
        "institutul",
        "anuarul",
    )

    for idx, line in enumerate(lines):
        norm = normalized_letters(line)
        if not any(label in norm for label in labels):
            continue

        value = ""
        if ":" in line:
            value = line.split(":", 1)[1].strip()
        elif " - " in line:
            value = line.split(" - ", 1)[1].strip()

        parts = [value] if value else []
        for follow in lines[idx + 1 : idx + 8]:
            follow_line = clean_line(follow)
            if not follow_line:
                break
            follow_norm = normalized_letters(follow_line)

            if any(term in follow_norm for term in stop_terms):
                break
            if re.match(r"^[\*\u2217]", follow_line):
                break
            if len(follow_line) > 200:
                break

            # Keywords continuation tends to be comma/semicolon or compact phrase lines.
            if "," in follow_line or ";" in follow_line or len(follow_line.split()) <= 14:
                parts.append(follow_line)
                continue
            break

        return normalize_keywords(" ".join(parts))

    return ""


def _section_allows_abstract(entry: dict) -> bool:
    section_norm = normalized_letters(entry.get("section", ""))
    if not section_norm:
        return False

    blocked = ("recenzii", "bookreviews", "note", "lectura", "memoriam", "restituiri")
    if any(token in section_norm for token in blocked):
        return False

    allowed = (
        "studii",
        "cercetari",
        "researchandstudies",
        "arhivadefolclor",
        "folklorearchive",
    )
    return any(token in section_norm for token in allowed)


def _looks_like_author_line(line: str) -> bool:
    line = clean_line(line)
    if not line or len(line) > 120 or any(ch.isdigit() for ch in line):
        return False
    if re.search(r"[.,;:!?\"“”]", line):
        return False
    words = [w for w in line.split() if re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", w)]
    if not (1 <= len(words) <= 4):
        return False
    return line == line.upper()


def _matches_author_hint(line: str, author_hint: str) -> bool:
    if not author_hint:
        return False
    line_norm = normalize_text(line)
    author_norm = normalize_text(author_hint)
    if not line_norm or not author_norm:
        return False

    parts = [part for part in author_norm.split() if part]
    return bool(parts) and all(part in line_norm for part in parts[:3])


def _is_heading_like_line(line: str) -> bool:
    cleaned = clean_line(line)
    letters = [ch for ch in cleaned if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
    if upper_ratio > 0.80 and len(cleaned.split()) >= 4:
        return True
    if cleaned.endswith("(Abstract)") or cleaned.endswith("(Résumé)") or cleaned.endswith("(Zusammenfassung)"):
        return True
    return False


def _keyword_line_index(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        norm = normalized_letters(line)
        if any(label in norm for label in KEYWORD_LABELS):
            return idx
    return -1


def _extract_abstract_from_first_page(lines: list[str], title: str, author_hint: str) -> str:
    keyword_idx = _keyword_line_index(lines)
    if keyword_idx <= 0:
        return ""

    title_idx = -1
    for idx, line in enumerate(lines[:30]):
        if line_matches_title(line, title):
            title_idx = idx
            break

    start = title_idx + 1 if title_idx >= 0 else 0

    # Skip author lines directly below title.
    while start < keyword_idx and _looks_like_author_line(lines[start]):
        start += 1

    abstract_parts: list[str] = []
    for idx in range(start, keyword_idx):
        line = clean_line(lines[idx])
        if not line:
            if abstract_parts:
                abstract_parts.append(" ")
            continue

        norm = normalized_letters(line)
        if norm.startswith("anuarularhiveidefolclor") or norm.startswith("thefolklorearchiveyearbook"):
            continue
        if re.match(r"^[\*\u2217]", line):
            # affiliation/footnote marker -> not abstract body
            continue
        if line_matches_title(line, title):
            continue
        if _matches_author_hint(line, author_hint) or _looks_like_author_line(line):
            continue
        if _is_heading_like_line(line):
            continue

        # Header-like abstract label rows should be ignored.
        if "abstract" in norm and len(line.split()) <= 18:
            continue

        abstract_parts.append(line)

    abstract = " ".join(abstract_parts)
    abstract = re.sub(r"\s+", " ", abstract).strip()
    if len(abstract) < 40:
        return ""
    return abstract


def _extract_affiliation(lines: list[str], raw_text: str) -> str:
    for line in lines:
        if re.match(r"^[\*\u2217]\s*", line):
            candidate = re.sub(r"^[\*\u2217]\s*", "", line).strip()
            if len(candidate) > 8:
                return candidate

    # Secondary pass: common institutional patterns.
    inst_patterns = [
        r"(Institutul[^\n]{8,240})",
        r"(Universitatea[^\n]{8,240})",
        r"(Academia[^\n]{8,240})",
        r"(Muzeul[^\n]{8,240})",
    ]
    for pattern in inst_patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return clean_line(match.group(1))

    return ""


def _fallback_unlabeled_abstract(lines: list[str], title: str) -> str:
    title_idx = -1
    for idx, line in enumerate(lines[:30]):
        if line_matches_title(line, title):
            title_idx = idx
            break

    # Candidate paragraphs near top area, before keyword lines and before body-like footnote noise.
    candidates: list[str] = []
    start = max(0, title_idx + 1)
    for idx in range(start, min(len(lines), start + 25)):
        line = lines[idx]
        norm = normalized_letters(line)
        if any(tok in norm for tok in ("keywords", "keyword", "cuvintecheie", "rezumat", "abstract")):
            continue
        if re.match(r"^[\*\u2217]", line):
            continue
        if len(line) < 90:
            continue
        block = _collect_block(
            lines,
            idx,
            stop_terms=("keywords", "keyword", "cuvintecheie", "rezumat", "abstract", "anuarul"),
            max_lines=14,
            max_chars=2200,
        )
        if block and len(block) >= 140:
            candidates.append(block)

    if not candidates:
        return ""

    # Pick candidate that is lexically closest to abstract style (dense sentence text).
    def score_candidate(text: str) -> tuple[int, int]:
        punctuation = text.count(".") + text.count(";") + text.count(":")
        words = len(text.split())
        return (punctuation, words)

    candidates.sort(key=score_candidate, reverse=True)
    return candidates[0]


def _compute_metadata_confidence(
    title_ok: bool,
    authors_ok: bool,
    has_abstract: bool,
    has_keywords: bool,
    text_quality: float,
) -> dict[str, float]:
    conf_title = 0.98 if title_ok else 0.60
    conf_authors = 0.96 if authors_ok else 0.55
    conf_abstract = min(0.98, (0.45 if has_abstract else 0.20) + 0.55 * text_quality)
    conf_keywords = min(0.98, (0.42 if has_keywords else 0.22) + 0.56 * text_quality)
    return {
        "conf_title": round(conf_title, 3),
        "conf_authors": round(conf_authors, 3),
        "conf_abstract": round(conf_abstract, 3),
        "conf_keywords": round(conf_keywords, 3),
    }


def parse_frontmatter(
    front_text: str,
    first_page_text: str,
    full_text: str,
    entry: dict,
    keyword_stopwords: set[str] | frozenset[str],
    text_quality: float,
) -> dict:
    """Parse metadata from first page(s), preserving TOC title/authors as source of truth."""
    raw_lines = [clean_line(line) for line in front_text.splitlines()]
    lines = [line for line in raw_lines if line]
    lines = strip_noise_lines(lines)

    first_page_lines = [clean_line(line) for line in first_page_text.splitlines()]
    first_page_lines = [line for line in first_page_lines if line]
    first_page_lines = strip_noise_lines(first_page_lines)

    review = is_review_entry(entry)

    # As requested, TOC remains source of truth for title/authors.
    title = entry.get("title", "").strip()
    toc_author = normalize_person_line(entry.get("author", ""))
    authors = toc_author or "N/A"

    affiliation = _extract_affiliation(lines, front_text)

    keywords_en = _extract_keywords_field(first_page_lines, labels=("keywords", "keyword", "schlusselworte", "motscles"))
    keywords_ro = _extract_keywords_field(first_page_lines, labels=("cuvintecheie",))

    abstract_en = ""
    if _section_allows_abstract(entry):
        abstract_en = _extract_abstract_from_first_page(first_page_lines, title, toc_author)

    # Keep RO abstract disabled as requested by editorial workflow.
    abstract_ro = ""

    doi = extract_doi_field(front_text)
    emails = extract_emails_field(front_text)

    if review:
        abstract_en = ""
        keywords_ro = ""
        keywords_en = ""
        doi = ""
        emails = ""

    merged_keywords = merge_keyword_fields(keywords_ro, keywords_en)
    if not review:
        merged_keywords = enforce_last_keyword_from_context(
            merged_keywords,
            abstract_en,
            full_text,
            keyword_stopwords,
        )

    keywords_ro = merged_keywords
    keywords_en = merged_keywords

    if abstract_en:
        # Abstract language can be EN/DE/FR; apply EN-specific repair only when detected.
        abstract_lang = detect_language(title=title, body_text=abstract_en)
        abstract_en = sanitize_abstract_text(abstract_en, lang_hint="en" if abstract_lang == "en" else "ro")

    language = detect_language(
        title=title,
        body_text=full_text,
        abstract_en=abstract_en,
        keywords_en=keywords_en,
    )

    conf = _compute_metadata_confidence(
        title_ok=bool(title),
        authors_ok=bool(authors and authors != "N/A"),
        has_abstract=bool(abstract_en),
        has_keywords=bool(keywords_en),
        text_quality=text_quality,
    )

    return {
        "title": title,
        "authors": authors,
        "affiliation": affiliation,
        "abstract_ro": abstract_ro,
        "abstract_en": abstract_en,
        "keywords_ro": keywords_ro,
        "keywords_en": keywords_en,
        "doi": doi,
        "emails": emails,
        "language": language,
        "is_review": review,
        **conf,
    }
