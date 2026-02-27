"""PDF extraction layer based on PyMuPDF with OCR fallback."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

try:
    import fitz  # type: ignore
except Exception as exc:  # pragma: no cover - import guard
    raise RuntimeError(
        "PyMuPDF is required for ingest. Install with: pip install PyMuPDF"
    ) from exc

try:
    from markitdown import MarkItDown  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    MarkItDown = None

from .config import OCR_DPI, OCR_LANGUAGES, TESSERACT_BIN, TMP_ROOT
from .text_cleanup import ligature_repair

LOGGER = logging.getLogger(__name__)
_MARKITDOWN_INSTANCE = None


def page_count(pdf_path: Path) -> int:
    """Return number of pages using PyMuPDF."""
    with fitz.open(pdf_path) as doc:
        return len(doc)


def _clean_markdown_output(text: str) -> str:
    cleaned = (text or "").replace("\ufeff", "").replace("\x00", "")
    cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip()


def _markitdown_instance():
    global _MARKITDOWN_INSTANCE
    if MarkItDown is None:
        return None
    if _MARKITDOWN_INSTANCE is None:
        _MARKITDOWN_INSTANCE = MarkItDown()
    return _MARKITDOWN_INSTANCE


def extract_markdown_with_markitdown(pdf_path: Path) -> str:
    """Extract markdown from a PDF using Microsoft MarkItDown."""
    converter = _markitdown_instance()
    if converter is None:
        return ""

    try:
        result = converter.convert(pdf_path)
    except Exception:
        LOGGER.exception("markitdown conversion failed for %s", pdf_path)
        return ""

    markdown = getattr(result, "markdown", "") or getattr(result, "text_content", "")
    return _clean_markdown_output(markdown)


def _extract_page_text(page: "fitz.Page") -> str:
    # text flag keeps natural reading order reasonably well for scholarly PDFs.
    text = page.get_text("text") or ""
    return ligature_repair(text)


def extract_text_range(pdf_path: Path, first_page: int, last_page: int) -> str:
    """Extract text from [first_page, last_page] inclusive, 1-based pages."""
    if first_page < 1:
        first_page = 1

    chunks: list[str] = []
    with fitz.open(pdf_path) as doc:
        total = len(doc)
        if total == 0:
            return ""
        start = min(first_page - 1, total - 1)
        end = min(last_page - 1, total - 1)
        if end < start:
            end = start

        for idx in range(start, end + 1):
            chunks.append(_extract_page_text(doc[idx]).strip())

    return "\n\n".join(part for part in chunks if part).strip()


def extraction_is_weak(text: str, min_chars: int = 600, min_words: int = 120) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if len(normalized) < min_chars:
        return True

    words = re.findall(r"[A-Za-zĂÂÎȘȚăâîșț\-]{3,}", normalized)
    if len(words) < min_words:
        return True

    letters = sum(1 for ch in normalized if ch.isalpha())
    ratio = letters / max(1, len(normalized))
    return ratio < 0.20


def _render_pages_for_ocr(pdf_path: Path, first_page: int, last_page: int, image_dir: Path) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []

    zoom = max(1.0, OCR_DPI / 72.0)
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(pdf_path) as doc:
        total = len(doc)
        start = max(0, first_page - 1)
        end = min(total - 1, last_page - 1)
        for idx in range(start, end + 1):
            pix = doc[idx].get_pixmap(matrix=matrix, colorspace=fitz.csGRAY)
            out_path = image_dir / f"page-{idx + 1:04d}.png"
            pix.save(out_path)
            rendered.append(out_path)

    return rendered


def ocr_extract_text_range(pdf_path: Path, first_page: int, last_page: int, temp_stem: str) -> str:
    """OCR fallback via Tesseract with multilingual profile."""
    if not Path(TESSERACT_BIN).exists():
        LOGGER.warning("Tesseract binary not found at %s", TESSERACT_BIN)
        return ""

    image_dir = TMP_ROOT / f"{temp_stem}-ocr"
    if image_dir.exists():
        shutil.rmtree(image_dir, ignore_errors=True)

    try:
        pages = _render_pages_for_ocr(pdf_path, first_page, last_page, image_dir)
    except Exception:
        LOGGER.exception("OCR render failed for %s", pdf_path)
        shutil.rmtree(image_dir, ignore_errors=True)
        return ""

    chunks: list[str] = []
    for image_path in pages:
        try:
            proc = subprocess.run(
                [
                    TESSERACT_BIN,
                    str(image_path),
                    "stdout",
                    "-l",
                    OCR_LANGUAGES,
                    "--oem",
                    "1",
                    "--psm",
                    "6",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            LOGGER.exception("Tesseract execution failed on %s", image_path)
            continue

        txt = (proc.stdout or "").strip()
        if txt:
            chunks.append(ligature_repair(txt))

    shutil.rmtree(image_dir, ignore_errors=True)
    return "\n\n".join(chunks).strip()


def extract_text_best_effort(
    pdf_path: Path,
    first_page: int,
    last_page: int,
    temp_stem: str,
    min_chars: int,
    min_words: int,
) -> tuple[str, str]:
    """Return (text, source) where source is 'fitz' or 'ocr'."""
    extracted = extract_text_range(pdf_path, first_page, last_page)
    if not extraction_is_weak(extracted, min_chars=min_chars, min_words=min_words):
        return extracted, "fitz"

    ocr_text = ocr_extract_text_range(pdf_path, first_page, last_page, temp_stem)
    if ocr_text and not extraction_is_weak(
        ocr_text,
        min_chars=max(220, min_chars // 2),
        min_words=max(35, min_words // 2),
    ):
        return ocr_text, "ocr"

    return ocr_text or extracted, "ocr" if ocr_text else "fitz"


def score_text_quality(text: str) -> float:
    """Simple quality score in [0,1] based on lexical health signals."""
    if not text:
        return 0.0

    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return 0.0

    words = re.findall(r"\b[\w\-]{2,}\b", compact, flags=re.UNICODE)
    if not words:
        return 0.0

    bad_tokens = 0
    for token in words:
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            bad_tokens += 1
            continue
        if "�" in token:
            bad_tokens += 1
            continue
        # Suspicious OCR splits: 'speci c', 'de ned' become tiny dangling pieces.
        if len(token) == 1 and token.lower() in {"c", "d", "e"}:
            bad_tokens += 1

    bad_ratio = bad_tokens / len(words)

    letter_ratio = sum(1 for ch in compact if ch.isalpha()) / max(1, len(compact))
    base = min(1.0, 0.35 + 0.75 * letter_ratio)
    penalty = min(0.45, bad_ratio * 1.8)
    score = max(0.0, min(1.0, base - penalty))
    return round(score, 3)


def find_text_hits(pdf_path: Path, needle_normalized: str, max_pages: int) -> list[int]:
    """Return 1-based page numbers containing normalized needle."""
    if not needle_normalized:
        return []

    from .text_cleanup import normalize_text

    hits: list[int] = []
    with fitz.open(pdf_path) as doc:
        limit = min(len(doc), max_pages)
        for idx in range(limit):
            page_text = normalize_text(_extract_page_text(doc[idx]))
            if needle_normalized in page_text:
                hits.append(idx + 1)
    return hits
