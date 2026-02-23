"""Configuration: paths, constants, issue definitions."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS_DIR.parent

DEFAULT_SOURCE_ROOT = ROOT.parent / "Anuarul Arhivei de Folclor (arhiva)"
SOURCE_ROOT = Path(os.environ.get("IAFAR_SOURCE_ROOT", str(DEFAULT_SOURCE_ROOT)))

OUT_ROOT = ROOT / "ingest" / "issues"
TMP_ROOT = ROOT / "tmp" / "pdfs" / "ingest"

# External tools.
TESSERACT_BIN = os.environ.get("TESSERACT_BIN", shutil.which("tesseract") or "/opt/homebrew/bin/tesseract")
PDFTOTEXT_BIN = os.environ.get("PDFTOTEXT_BIN", shutil.which("pdftotext") or "")

# OCR settings.
OCR_LANGUAGES = os.environ.get("OCR_LANGUAGES", "ron+eng+deu+fra")
OCR_DPI = int(os.environ.get("OCR_DPI", "300"))

# Journal constants.
DEFAULT_AFFILIATION = ""

PUBLISHER = "Academia Română – Filiala Cluj-Napoca · Institutul „Arhiva de Folclor a Academiei Române”"
ISSN = "1220-3661"
JOURNAL_NAME = "Anuarul Arhivei de Folclor / The Folklore Archive Yearbook"
JOURNAL_ABBR = "AAF"
JOURNAL_URL = "https://www.iafar.ro"
JOURNAL_DESCRIPTION = (
    "Publicație științifică a Academiei Române – Filiala Cluj-Napoca, "
    "Institutul „Arhiva de Folclor a Academiei Române”. "
    "Contact: str. Republicii nr. 59, 400015 Cluj-Napoca · "
    "Tel/Fax +40-264-591864 · Email: anuar@iafar.ro."
)

KEYWORD_STOPWORDS = frozenset(
    {
        "si",
        "sau",
        "din",
        "prin",
        "pentru",
        "despre",
        "asupra",
        "intre",
        "intr",
        "acest",
        "aceasta",
        "aceste",
        "acelor",
        "care",
        "este",
        "sunt",
        "fost",
        "fiind",
        "fara",
        "dupa",
        "cu",
        "de",
        "la",
        "pe",
        "in",
        "un",
        "o",
        "a",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "these",
        "article",
        "study",
        "research",
        "folklore",
        "archive",
        "romania",
        "romanian",
        "rezumat",
        "abstract",
        "keyword",
        "keywords",
        "cuvinte",
        "cheie",
        "institutul",
        "anuarul",
        "arhivei",
        "folclor",
    }
)

ISSUES_INPUT = [
    {
        "id": "1",
        "slug": "aaf-xxv-xxvi-2022",
        "volume": "25-26",
        "number": "1",
        "year": "2022",
        "date_published": "2022-12-31",
        "title": "Anuarul Arhivei de Folclor XXV-XXVI",
        "src_pdf": SOURCE_ROOT / "Anuarul Arhivei de Folclor XXV-XXVI (2022).pdf",
    },
    {
        "id": "2",
        "slug": "aaf-xxvii-2023",
        "volume": "27",
        "number": "1",
        "year": "2023",
        "date_published": "2023-12-31",
        "title": "Anuarul Arhivei de Folclor XXVII",
        "src_pdf": SOURCE_ROOT / "Anuarul Arhivei de Folclor XXVII (2023).pdf",
    },
    {
        "id": "3",
        "slug": "aaf-xxviii-2024",
        "volume": "28",
        "number": "1",
        "year": "2024",
        "date_published": "2024-12-31",
        "title": "Anuarul Arhivei de Folclor XXVIII",
        "src_pdf": SOURCE_ROOT / "Anuarul Arhivei de Folclor XXVIII (2024).pdf",
    },
    {
        "id": "4",
        "slug": "aaf-xxix-2025",
        "volume": "29",
        "number": "1",
        "year": "2025",
        "date_published": "2025-12-20",
        "title": "Anuarul Arhivei de Folclor XXIX",
        "src_pdf": SOURCE_ROOT / "Anuarul Arhivei de Folclor XXIX (2025).pdf",
    },
]
