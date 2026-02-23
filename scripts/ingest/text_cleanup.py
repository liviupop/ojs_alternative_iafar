"""Text cleanup and normalization helpers for ingest pipeline."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

LIGATURE_MAP = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

# Frequent OCR/encoding artifacts observed in AAF PDFs.
COMMON_WORD_FIXES = {
    "inuential": "influential",
    "gure": "figure",
    "eld": "field",
    "eldwork": "fieldwork",
    "oers": "offers",
    "ourish": "flourish",
    "speci c": "specific",
    "signi cant": "significant",
    "de ned": "defined",
    "rst": "first",
    "inseted": "inserted",
    "bibliology": "bibliology",  # stable canonical spelling guard
}


def clean_line(value: str) -> str:
    """Normalize a single line by collapsing whitespace and NBSP variants."""
    value = strip_control_chars(value)
    value = value.replace("\u00a0", " ")
    value = value.replace("\u2009", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalized_letters(value: str) -> str:
    """Strip diacritics and non-letter chars for fuzzy structural matching."""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z]+", "", value.lower())


def normalize_text(value: str) -> str:
    """Normalize text for lexical comparisons and deduping."""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def strip_control_chars(value: str) -> str:
    """Drop control characters that leak from OCR/PDF extraction."""
    if not value:
        return ""

    kept: list[str] = []
    for ch in value:
        if ch in ("\n", "\t"):
            kept.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("C"):
            continue
        kept.append(ch)
    return "".join(kept)


def ensure_terminal_period(value: str) -> str:
    """Ensure abstract-like text ends in sentence punctuation."""
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return ""
    if text[-1] not in ".!?":
        text = f"{text}."
    return text


def ligature_repair(text: str) -> str:
    """Repair explicit ligatures and common dropped-ligature artifacts."""
    if not text:
        return ""

    out = text
    for glyph, replacement in LIGATURE_MAP.items():
        out = out.replace(glyph, replacement)

    # Remove obvious OCR marker symbols that leak into extracted text.
    out = re.sub(r"[□■☒☐]+", " ", out)

    # Fix split words caused by missing ligature components.
    out = re.sub(r"\bspeci\s+c\b", "specific", out, flags=re.IGNORECASE)
    out = re.sub(r"\bsigni\s+cant\b", "significant", out, flags=re.IGNORECASE)
    out = re.sub(r"\bde\s+ned\b", "defined", out, flags=re.IGNORECASE)

    # Apply dictionary-level corrections with word boundaries.
    for src, dst in COMMON_WORD_FIXES.items():
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)

    return out


def sanitize_abstract_text(value: str, lang_hint: str = "en") -> str:
    """Normalize abstract text and fix common OCR degradations.

    Rules:
    - remove controls
    - repair ligatures/artifacts
    - normalize whitespace
    - for English, repair dropped initial "Th" -> "The" in sentence starts
    - ensure terminal punctuation
    """
    text = strip_control_chars(value or "")
    text = ligature_repair(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    if lang_hint == "en":
        # Sentence/headline starts where OCR often loses "Th" and leaves "e".
        text = re.sub(r"(^|[.!?]\s+)e\s+(?=[A-Za-z])", r"\1The ", text)

        # Standalone e token before a word can be a dropped "the".
        def _fix_isolated_e(match: re.Match[str]) -> str:
            start = match.start()
            prefix = text[:start]
            prev = ""
            for ch in reversed(prefix):
                if not ch.isspace():
                    prev = ch
                    break
            if not prev or prev in ".!?;:\n":
                return "The"
            return "the"

        text = re.sub(r"\b[eE]\b(?=\s+[A-Za-z])", _fix_isolated_e, text)

    return ensure_terminal_period(text)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:120] or "articol"


def is_upperish(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return (upper / len(letters)) > 0.82


def normalize_person_line(value: str) -> str:
    value = re.sub(r"[\*\d]+$", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        return ""

    def _cap_hyphenated(token: str) -> str:
        return "-".join(part.capitalize() for part in token.split("-") if part)

    if value == value.upper():
        return " ".join(_cap_hyphenated(token) for token in value.split())

    tokens: list[str] = []
    for token in value.split():
        clean = re.sub(r"[^A-Za-zĂÂÎȘȚăâîșț\-]", "", token)
        if clean and clean == clean.upper() and len(clean) > 1:
            tokens.append(_cap_hyphenated(clean))
        else:
            tokens.append(token)
    return " ".join(tokens).strip()


def strip_noise_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        norm = normalized_letters(line)
        if not norm:
            continue
        if norm.startswith("anuarularhiveidefolclor") and "nr" in norm:
            continue
        if norm.startswith("thefolklorearchiveyearbook"):
            continue
        cleaned.append(line)
    return cleaned


def normalize_keywords(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ;,")
    if not value:
        return ""

    parts: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[;,]", value):
        cleaned = re.sub(r"\s+", " ", token).strip(" .:-–—;,\t")
        if not cleaned:
            continue
        if len(cleaned) > 80 or len(cleaned.split()) > 8:
            continue

        norm = normalize_text(cleaned)
        if not norm:
            continue
        if norm in seen:
            continue
        if norm in {"keywords", "keyword", "cuvinte cheie"}:
            continue
        seen.add(norm)
        parts.append(cleaned)

    return ", ".join(parts)


def merge_keyword_fields(*values: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = normalize_keywords(value)
        if not normalized:
            continue
        for token in [part.strip() for part in normalized.split(",") if part.strip()]:
            key = normalize_text(token)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(token)

    return ", ".join(merged)


def keyword_in_context(keyword: str, context: str) -> bool:
    key = normalize_text(keyword)
    ctx = normalize_text(context)
    if not key or not ctx:
        return False
    return re.search(rf"\b{re.escape(key)}\b", ctx) is not None


def derive_keyword_from_context(context: str, existing_keywords: list[str], stopwords: set[str] | frozenset[str]) -> str:
    ctx = normalize_text(context)
    if not ctx:
        return ""

    tokens = re.findall(r"\b[a-z]{4,}\b", ctx)
    if not tokens:
        return ""

    existing = {normalize_text(item) for item in existing_keywords if item}
    counts = Counter(tokens)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))

    for token, freq in ranked:
        if token in stopwords:
            continue
        if token in existing:
            continue
        if freq <= 1 and len(token) < 6:
            continue
        return token

    return ""


def enforce_last_keyword_from_context(
    keywords_value: str,
    abstract_text: str,
    full_text: str,
    stopwords: set[str] | frozenset[str],
) -> str:
    normalized = normalize_keywords(keywords_value)
    keywords = [part.strip() for part in normalized.split(",") if part.strip()]
    context = (abstract_text or "").strip() or (full_text or "").strip()
    if not context:
        return normalized

    if not keywords:
        candidate = derive_keyword_from_context(context, [], stopwords)
        return candidate

    last = keywords[-1]
    if keyword_in_context(last, context):
        return ", ".join(keywords)

    replacement = derive_keyword_from_context(context, keywords[:-1], stopwords)
    if replacement:
        keywords[-1] = replacement
    return ", ".join(keywords)


def normalize_full_text(raw_text: str) -> str:
    """Normalize extracted full text while preserving paragraph breaks."""
    text = (raw_text or "").replace("\r", "")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
