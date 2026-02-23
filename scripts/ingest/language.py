"""Language detection for academic journal articles."""

from __future__ import annotations

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0

SUPPORTED_CODES: set[str] = {"ro", "en", "de", "fr"}

_GERMAN_MARKERS = [" zur ", " deutsch", " über ", " die ", " und ", " des "]
_ENGLISH_MARKERS = [" the ", " and ", " study ", " interview ", " review "]
_FRENCH_MARKERS = [" le ", " la ", " les ", " des ", " une ", " et ", " résumé "]


def _heuristic_language(text: str) -> str:
    padded = f" {text.lower()} "
    if any(marker in padded for marker in _GERMAN_MARKERS):
        return "de"
    if any(marker in padded for marker in _FRENCH_MARKERS):
        return "fr"
    if any(marker in padded for marker in _ENGLISH_MARKERS):
        return "en"
    return "ro"


def _safe_detect(text: str) -> str | None:
    if not text or len(text.strip()) < 30:
        return None
    try:
        code = detect(text)
    except LangDetectException:
        return None
    if code in SUPPORTED_CODES:
        return code
    return None


def detect_language(
    title: str,
    body_text: str = "",
    abstract_en: str = "",
    keywords_en: str = "",
) -> str:
    """Return ISO 639-1 language code from supported set."""
    if body_text and len(body_text.strip()) > 100:
        code = _safe_detect(body_text)
        if code:
            return code

    combined = " ".join(filter(None, [title, abstract_en]))
    code = _safe_detect(combined)
    if code:
        return code

    context = " ".join(filter(None, [title, abstract_en, keywords_en]))
    return _heuristic_language(context)
