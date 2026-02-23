# PDF Ingest Pipeline v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Ghostscript-based text extraction with PyMuPDF to fix ligature corruption, add modular architecture with tests, improve OCR fallback and language detection.

**Architecture:** Modular Python package under scripts/ingest/ with PyMuPDF as primary extractor, Ghostscript+Tesseract as OCR fallback only. CLI via argparse. All existing functionality preserved.

**Tech Stack:** PyMuPDF (fitz), langdetect, pytest, Tesseract 5.5, Ghostscript 10.06

---

### Task 1: Create package structure and requirements.txt

**Files:**
- Create: `scripts/ingest/__init__.py`
- Create: `scripts/ingest/config.py`
- Create: `scripts/requirements.txt`
- Create: `scripts/tests/__init__.py`

### Task 2: Implement text_cleanup.py — ligature repair + normalization

**Files:**
- Create: `scripts/ingest/text_cleanup.py`
- Create: `scripts/tests/test_text_cleanup.py`

Core functions: clean_line, normalized_letters, normalize_text, strip_control_chars,
sanitize_abstract_text, slugify, normalize_person_line, normalize_keywords,
merge_keyword_fields, ensure_terminal_period, ligature_repair (NEW)

### Task 3: Implement pdf_extract.py — PyMuPDF extraction + OCR fallback

**Files:**
- Create: `scripts/ingest/pdf_extract.py`

Core functions: extract_text_range (fitz), page_count (fitz), extraction_is_weak,
extract_text_best_effort, ocr_extract_text_range (GS+tesseract fallback)

### Task 4: Implement toc_parser.py

**Files:**
- Create: `scripts/ingest/toc_parser.py`
- Create: `scripts/tests/test_toc_parser.py`

Core functions: parse_toc_entries, is_upperish, extract_review_author_from_title

### Task 5: Implement language.py

**Files:**
- Create: `scripts/ingest/language.py`
- Create: `scripts/tests/test_language.py`

### Task 6: Implement metadata.py — frontmatter parsing

**Files:**
- Create: `scripts/ingest/metadata.py`
- Create: `scripts/tests/test_metadata.py`

### Task 7: Implement splitter.py — PDF splitting with PyMuPDF

**Files:**
- Create: `scripts/ingest/splitter.py`

### Task 8: Implement manifest.py — JSON/JS generation

**Files:**
- Create: `scripts/ingest/manifest.py`

### Task 9: Rewrite build_ingest_library.py as CLI orchestrator

**Files:**
- Modify: `scripts/build_ingest_library.py`

### Task 10: Run full pipeline and verify output quality

Compare v2 output with v1 output for ligature fixes and metadata quality.
