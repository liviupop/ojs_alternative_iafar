"""PDF splitting utilities based on PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore


def split_article_pdf(src_pdf: Path, out_pdf: Path, first_page: int, last_page: int) -> None:
    """Split a page range from source PDF into article PDF.

    Parameters are 1-based inclusive page numbers.
    """
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(src_pdf) as src:
        total = len(src)
        if total == 0:
            raise ValueError(f"Empty PDF: {src_pdf}")

        start = max(0, first_page - 1)
        end = min(total - 1, last_page - 1)
        if end < start:
            end = start

        with fitz.open() as dst:
            dst.insert_pdf(src, from_page=start, to_page=end)
            dst.save(out_pdf)
