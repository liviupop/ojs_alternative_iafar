#!/usr/bin/env python3
from collections import Counter
import datetime
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path('/Users/liviupop/Downloads/ojs_alternative_iafar')
SOURCE_ROOT = Path('/Users/liviupop/Downloads/Anuarul Arhivei de Folclor (arhiva)')
OUT_ROOT = ROOT / 'ingest' / 'issues'
TMP_ROOT = ROOT / 'tmp' / 'pdfs' / 'ingest'
GS_BIN = '/opt/homebrew/bin/gs'
TESSERACT_BIN = '/opt/homebrew/bin/tesseract'

DEFAULT_AFFILIATION = 'Institutul „Arhiva de Folclor a Academiei Române”, Cluj-Napoca'

KEYWORD_STOPWORDS = {
    'si', 'sau', 'din', 'prin', 'pentru', 'despre', 'asupra', 'intre', 'intr',
    'acest', 'aceasta', 'aceste', 'acelor', 'care', 'este', 'sunt', 'fost',
    'fiind', 'fara', 'dupa', 'cu', 'de', 'la', 'pe', 'in', 'un', 'o', 'a',
    'the', 'and', 'for', 'with', 'from', 'into', 'that', 'this', 'these',
    'article', 'study', 'research', 'folklore', 'archive', 'romania', 'romanian',
    'rezumat', 'abstract', 'keyword', 'keywords', 'cuvinte', 'cheie',
    'institutul', 'anuarul', 'arhivei', 'folclor',
}

ISSUES_INPUT = [
    {
        'id': '1',
        'slug': 'aaf-xxv-xxvi-2022',
        'volume': '25-26',
        'number': '1',
        'year': '2022',
        'date_published': '2022-12-31',
        'title': 'Anuarul Arhivei de Folclor XXV-XXVI',
        'src_pdf': SOURCE_ROOT / 'Anuarul Arhivei de Folclor XXV-XXVI (2022).pdf',
    },
    {
        'id': '2',
        'slug': 'aaf-xxvii-2023',
        'volume': '27',
        'number': '1',
        'year': '2023',
        'date_published': '2023-12-31',
        'title': 'Anuarul Arhivei de Folclor XXVII',
        'src_pdf': SOURCE_ROOT / 'Anuarul Arhivei de Folclor XXVII (2023).pdf',
    },
    {
        'id': '3',
        'slug': 'aaf-xxviii-2024',
        'volume': '28',
        'number': '1',
        'year': '2024',
        'date_published': '2024-12-31',
        'title': 'Anuarul Arhivei de Folclor XXVIII',
        'src_pdf': SOURCE_ROOT / 'Anuarul Arhivei de Folclor XXVIII (2024).pdf',
    },
    {
        'id': '4',
        'slug': 'aaf-xxix-2025',
        'volume': '29',
        'number': '1',
        'year': '2025',
        'date_published': '2025-12-20',
        'title': 'Anuarul Arhivei de Folclor XXIX',
        'src_pdf': SOURCE_ROOT / 'Anuarul Arhivei de Folclor XXIX (2025).pdf',
    },
]


def gs_extract_text(pdf_path: Path, out_txt: Path, first: int, last: int) -> None:
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        GS_BIN,
        '-q',
        '-sDEVICE=txtwrite',
        f'-dFirstPage={first}',
        f'-dLastPage={last}',
        '-o',
        str(out_txt),
        str(pdf_path),
    ]
    subprocess.run(cmd, check=True)


def gs_page_count(pdf_path: Path) -> int:
    cmd = [
        GS_BIN,
        '-q',
        '-sDEVICE=txtwrite',
        '-dFirstPage=99999',
        '-dLastPage=99999',
        '-o',
        '/tmp/ignore-gs-pagecount.txt',
        str(pdf_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    msg = (proc.stdout or '') + '\n' + (proc.stderr or '')
    match = re.search(r'number of pages in the file:\s*(\d+)', msg)
    if not match:
        raise RuntimeError(f'Cannot detect page count for {pdf_path}')
    return int(match.group(1))


def split_article_pdf(src_pdf: Path, out_pdf: Path, first_page: int, last_page: int) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        GS_BIN,
        '-q',
        '-sDEVICE=pdfwrite',
        '-dCompatibilityLevel=1.4',
        f'-dFirstPage={first_page}',
        f'-dLastPage={last_page}',
        '-o',
        str(out_pdf),
        str(src_pdf),
    ]
    subprocess.run(cmd, check=True)


def extract_text_range(pdf_path: Path, first_page: int, last_page: int, temp_name: str) -> str:
    out_txt = TMP_ROOT / temp_name
    gs_extract_text(pdf_path, out_txt, first_page, last_page)
    return out_txt.read_text(errors='ignore')


def ocr_extract_text_range(pdf_path: Path, first_page: int, last_page: int, temp_name: str) -> str:
    if not Path(TESSERACT_BIN).exists():
        return ''

    image_dir = TMP_ROOT / f'{Path(temp_name).stem}-ocr'
    if image_dir.exists():
        shutil.rmtree(image_dir, ignore_errors=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = image_dir / 'page-%03d.png'
    gs_cmd = [
        GS_BIN,
        '-q',
        '-dSAFER',
        '-dBATCH',
        '-dNOPAUSE',
        '-sDEVICE=pnggray',
        '-r220',
        f'-dFirstPage={first_page}',
        f'-dLastPage={last_page}',
        f'-sOutputFile={output_pattern}',
        str(pdf_path),
    ]
    try:
        subprocess.run(gs_cmd, check=True)
    except subprocess.CalledProcessError:
        shutil.rmtree(image_dir, ignore_errors=True)
        return ''

    chunks: list[str] = []
    for image_path in sorted(image_dir.glob('page-*.png')):
        try:
            proc = subprocess.run(
                [TESSERACT_BIN, str(image_path), 'stdout', '-l', 'eng', '--oem', '1', '--psm', '6'],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            continue
        text = (proc.stdout or '').strip()
        if text:
            chunks.append(text)

    shutil.rmtree(image_dir, ignore_errors=True)
    return '\n\n'.join(chunks).strip()


def clean_line(value: str) -> str:
    value = value.replace('\u00a0', ' ')
    value = value.replace('\u2009', ' ')
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def normalized_letters(value: str) -> str:
    value = unicodedata.normalize('NFD', value)
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^a-z]+', '', value.lower())


def normalize_text(value: str) -> str:
    value = unicodedata.normalize('NFD', value)
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    value = value.lower()
    value = re.sub(r'[^a-z0-9 ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def strip_control_chars(value: str) -> str:
    if not value:
        return ''
    kept = []
    for ch in value:
        if ch in ('\n', '\t'):
            kept.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat.startswith('C'):
            continue
        kept.append(ch)
    return ''.join(kept)


def ensure_terminal_period(value: str) -> str:
    text = re.sub(r'\s+', ' ', (value or '').strip())
    if not text:
        return ''
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def sanitize_abstract_text(value: str, lang_hint: str = 'en') -> str:
    text = strip_control_chars(value or '')
    text = text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    # OCR marker leftovers observed as boxed symbols before "e paper"/"e resulting ..."
    text = re.sub(r'[□■☒☐]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''

    if lang_hint == 'en':
        # Common OCR artifact in scanned PDFs: missing initial "Th" in "The".
        text = re.sub(r'(^|[.!?]\s+)\s*e\s+(?=[A-Za-z])', r'\1The ', text)
        text = re.sub(r'^e\s+(?=[A-Za-z])', 'The ', text)
        def fix_isolated_e(match: re.Match) -> str:
            idx = match.start()
            prefix = text[:idx]
            prev_nonspace = ''
            for ch in reversed(prefix):
                if not ch.isspace():
                    prev_nonspace = ch
                    break
            if not prev_nonspace or prev_nonspace in '.!?;:\n':
                return 'The'
            return 'the'
        # OCR sometimes drops "th" and leaves just "e" as a standalone token.
        text = re.sub(r'\b[eE]\b(?=\s+[A-Za-z])', fix_isolated_e, text)
        # Frequent OCR misspellings in extracted abstracts.
        replacements = [
            (r'\beld\b', 'field'),
            (r'\brst\b', 'first'),
            (r'\binseted\b', 'inserted'),
        ]
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return ensure_terminal_period(text)


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:120] or 'articol'


def is_upperish(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return (upper / len(letters)) > 0.82


def normalize_person_line(value: str) -> str:
    value = re.sub(r'[\*\d]+$', '', value).strip()
    value = re.sub(r'\s+', ' ', value)
    if not value:
        return ''
    if value == value.upper():
        return ' '.join(token.capitalize() for token in value.split())
    tokens = []
    for token in value.split():
        clean = re.sub(r'[^A-Za-zĂÂÎȘȚăâîșț\-]', '', token)
        if clean and clean == clean.upper() and len(clean) > 1:
            tokens.append(clean.capitalize())
        else:
            tokens.append(token)
    return ' '.join(tokens).strip()


def strip_noise_lines(lines: list[str]) -> list[str]:
    cleaned = []
    for line in lines:
        norm = normalized_letters(line)
        if not norm:
            continue
        if norm.startswith('anuarularhiveidefolclor') and 'nr' in norm:
            continue
        if norm.startswith('thefolklorearchiveyearbook'):
            continue
        cleaned.append(line)
    return cleaned


def extract_review_author_from_title(title: str) -> str:
    match = re.search(r'\(([^()]{3,120})\)\s*$', title or '')
    if not match:
        return ''
    candidate = normalize_person_line(match.group(1).strip())
    if len(candidate.split()) < 2:
        return ''
    return candidate


def parse_toc_entries(toc_text: str) -> list[dict]:
    lines = [clean_line(line) for line in toc_text.splitlines()]
    lines = [line for line in lines if line]

    start_idx = next((i for i, line in enumerate(lines) if 'cuprins' in normalized_letters(line)), None)
    if start_idx is None:
        return []

    end_idx = next(
        (
            i
            for i, line in enumerate(lines[start_idx + 1 :], start_idx + 1)
            if any(marker in normalized_letters(line) for marker in ('contents', 'sommario', 'sommaire', 'inhalt'))
        ),
        len(lines),
    )

    toc_lines = lines[start_idx + 1 : end_idx]
    entries = []
    current_author = ''
    current_section = ''
    pending_title_parts: list[str] = []

    for line in toc_lines:
        if not line:
            continue

        section_match = re.match(r'^([IVXLCM]+)\.?\s+(.+)$', line, re.IGNORECASE)
        if section_match and is_upperish(line):
            current_section = clean_line(section_match.group(2))
            current_author = ''
            pending_title_parts = []
            continue

        line_page_match = re.match(r'^(.*?)(\d{1,4})\s*$', line)
        if line_page_match:
            title = clean_line(line_page_match.group(1))
            page = int(line_page_match.group(2))
            if pending_title_parts:
                title = clean_line(' '.join(pending_title_parts + [title]))
                pending_title_parts = []
            if len(title) >= 8 and not is_upperish(title):
                author_value = current_author
                section_norm = normalized_letters(current_section)
                if any(token in section_norm for token in ('recenzii', 'bookreviews', 'bookreview')):
                    review_author = extract_review_author_from_title(title)
                    if review_author:
                        author_value = review_author
                entries.append(
                    {
                        'author': author_value,
                        'title': title,
                        'start_page': page,
                        'section': current_section,
                    }
                )
            continue

        if is_upperish(line) and len(line) <= 140 and not any(ch.isdigit() for ch in line):
            current_author = normalize_person_line(line)
            pending_title_parts = []
            continue

        pending_title_parts.append(line)

    deduped = []
    seen = set()
    for entry in entries:
        key = (entry['start_page'], entry['title'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    deduped.sort(key=lambda item: item['start_page'])
    return deduped


def detect_language(title: str, abstract_en: str = '', keywords_en: str = '') -> str:
    lower_title = f" {title.lower()} "
    lower_context = f" {title.lower()} {abstract_en.lower()} {keywords_en.lower()} "
    if any(token in lower_context for token in [' zur ', ' deutsch', ' über ']):
        return 'de'
    if any(token in lower_title for token in [' the ', ' and ', 'interview', 'study ', 'review ']):
        return 'en'
    return 'ro'


def normalize_keywords(value: str) -> str:
    value = re.sub(r'\s+', ' ', value).strip(' ;,')
    if not value:
        return ''
    if '.' in value:
        first = value.split('.', 1)[0].strip()
        if (',' in first or ';' in first) and len(first) >= 12:
            value = first
    parts: list[str] = []
    seen: set[str] = set()
    for token in re.split(r'[;,]', value):
        cleaned = re.sub(r'\s+', ' ', token).strip(' .:-–—;,\t')
        if not cleaned:
            continue
        if len(cleaned) > 80:
            continue
        if len(cleaned.split()) > 8:
            continue
        norm = normalize_text(cleaned)
        if not norm:
            continue
        if norm in seen:
            continue
        if norm in ('keywords', 'keyword', 'cuvinte cheie'):
            continue
        seen.add(norm)
        parts.append(cleaned)
    return ', '.join(parts)


def merge_keyword_fields(*values: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_keywords(value)
        if not normalized:
            continue
        for token in [part.strip() for part in normalized.split(',') if part.strip()]:
            key = normalize_text(token)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(token)
    return ', '.join(merged)


def keyword_in_context(keyword: str, context: str) -> bool:
    key = normalize_text(keyword)
    ctx = normalize_text(context)
    if not key or not ctx:
        return False
    return re.search(rf'\b{re.escape(key)}\b', ctx) is not None


def derive_keyword_from_context(context: str, existing_keywords: list[str]) -> str:
    ctx = normalize_text(context)
    if not ctx:
        return ''
    tokens = re.findall(r'\b[a-z]{4,}\b', ctx)
    if not tokens:
        return ''

    existing = {normalize_text(item) for item in existing_keywords if item}
    counts = Counter(tokens)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    for token, freq in ranked:
        if token in KEYWORD_STOPWORDS:
            continue
        if token in existing:
            continue
        if freq <= 1 and len(token) < 6:
            continue
        return token
    return ''


def enforce_last_keyword_from_context(keywords_value: str, abstract_text: str, full_text: str) -> str:
    normalized = normalize_keywords(keywords_value)
    keywords = [part.strip() for part in normalized.split(',') if part.strip()]
    context = (abstract_text or '').strip() or (full_text or '').strip()
    if not context:
        return normalized

    if not keywords:
        candidate = derive_keyword_from_context(context, [])
        return candidate

    last = keywords[-1]
    if keyword_in_context(last, context):
        return ', '.join(keywords)

    replacement = derive_keyword_from_context(context, keywords[:-1])
    if replacement:
        keywords[-1] = replacement
    return ', '.join(keywords)


def extract_keywords_field(lines: list[str], labels: tuple[str, ...]) -> str:
    stop_terms = ('keywords', 'keyword', 'cuvintecheie', 'rezumat', 'abstract', 'institutul', 'anuarul')
    for idx, line in enumerate(lines):
        norm = normalized_letters(line)
        if not any(label in norm for label in labels):
            continue

        value = ''
        if ':' in line:
            value = line.split(':', 1)[1].strip()
        elif ' - ' in line:
            value = line.split(' - ', 1)[1].strip()

        parts = [value] if value else []
        for follow in lines[idx + 1 : idx + 6]:
            follow_line = clean_line(follow)
            follow_norm = normalized_letters(follow_line)
            if not follow_line:
                break
            if any(term in follow_norm for term in stop_terms):
                break
            if re.match(r'^[\*\u2217]', follow_line):
                break
            if len(follow_line) > 160:
                break
            # Keywords continuation is usually short and comma/semicolon-separated.
            if not ((',' in follow_line) or (';' in follow_line) or (len(follow_line.split()) <= 12)):
                break
            parts.append(follow_line)
            if '.' in ' '.join(parts):
                break

        return normalize_keywords(' '.join(parts))
    return ''


def extract_doi_field(text: str) -> str:
    if not text:
        return ''
    match = re.search(r'(?:https?://doi\.org/|doi\s*:?\s*)(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', text, re.IGNORECASE)
    if not match:
        return ''
    doi = match.group(1).strip().rstrip('.,;)')
    return doi


def extract_emails_field(text: str) -> str:
    if not text:
        return ''
    emails = re.findall(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}', text, flags=re.IGNORECASE)
    deduped = []
    seen = set()
    for email in emails:
        low = email.lower()
        if low in seen:
            continue
        seen.add(low)
        deduped.append(email)
    return '; '.join(deduped)


def find_offset(pdf_path: Path, first_entry: dict | None) -> int:
    if not first_entry:
        return 0

    needle = normalize_text(first_entry['title'])[:50]
    printed_start = int(first_entry['start_page'])
    tmp_page = TMP_ROOT / 'single-page.txt'
    hits = []
    upper_bound = min(140, printed_start + 80)

    for page in range(1, upper_bound + 1):
        gs_extract_text(pdf_path, tmp_page, page, page)
        page_text = normalize_text(tmp_page.read_text(errors='ignore'))
        if needle and needle in page_text:
            hits.append(page)

    candidates = [page for page in hits if page >= printed_start]
    if candidates:
        return candidates[0] - printed_start
    return 0


def line_matches_title(line: str, title: str) -> bool:
    line_n = normalize_text(line)
    title_n = normalize_text(title)
    if not line_n or not title_n:
        return False
    if line_n in title_n or title_n in line_n:
        return True
    title_tokens = title_n.split()
    if len(title_tokens) < 3:
        return False
    return sum(1 for tok in title_tokens[:6] if tok in line_n) >= 3


def looks_like_author_line(line: str) -> bool:
    line = clean_line(line)
    if not line or ':' in line:
        return False
    if len(line) < 4 or len(line) > 120:
        return False
    norm = normalized_letters(line)
    if any(token in norm for token in ('keywords', 'cuvintecheie', 'abstract', 'rezumat', 'institutul', 'anuarul')):
        return False
    words = [w for w in line.replace('*', '').split() if re.search(r'[A-Za-zĂÂÎȘȚăâîșț]', w)]
    if len(words) < 2 or len(words) > 9:
        return False
    if is_upperish(line) and len(words) > 4:
        return False
    return True


def collect_block(lines: list[str], start_idx: int, stop_terms: tuple[str, ...], max_lines: int, max_chars: int) -> str:
    buf = []
    for idx in range(start_idx, min(len(lines), start_idx + max_lines)):
        line = clean_line(lines[idx])
        if not line:
            if buf:
                break
            continue
        norm = normalized_letters(line)
        if any(term in norm for term in stop_terms):
            break
        if re.match(r'^[\*\u2217]', line):
            break
        if norm.startswith('anuarularhiveidefolclor'):
            break
        buf.append(line)
        if sum(len(part) for part in buf) >= max_chars:
            break
    text = ' '.join(buf)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_labeled_field(lines: list[str], labels: tuple[str, ...], stop_terms: tuple[str, ...], max_lines: int = 8, max_chars: int = 900) -> str:
    for idx, line in enumerate(lines):
        norm = normalized_letters(line)
        if not any(label in norm for label in labels):
            continue

        value = ''
        if ':' in line:
            value = line.split(':', 1)[1].strip()
        elif ' - ' in line:
            value = line.split(' - ', 1)[1].strip()

        rest = collect_block(lines, idx + 1, stop_terms=stop_terms, max_lines=max_lines, max_chars=max_chars)
        merged = f"{value} {rest}".strip()
        merged = re.sub(r'\s+', ' ', merged)
        merged = merged.strip(' ;,')
        if merged.endswith('.'):
            merged = merged[:-1].strip()
        if merged:
            return merged
    return ''


def normalize_full_text(raw_text: str) -> str:
    text = raw_text.replace('\r', '')
    text = re.sub(r'(?<=\w)-\n(?=\w)', '', text)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extraction_is_weak(text: str, min_chars: int = 600, min_words: int = 120) -> bool:
    normalized = normalize_full_text(text or '')
    if len(normalized) < min_chars:
        return True
    words = re.findall(r'[A-Za-zĂÂÎȘȚăâîșț\-]{3,}', normalized)
    if len(words) < min_words:
        return True
    letters = sum(1 for ch in normalized if ch.isalpha())
    ratio = letters / max(1, len(normalized))
    return ratio < 0.20


def extract_text_best_effort(pdf_path: Path, first_page: int, last_page: int, temp_name: str, min_chars: int, min_words: int) -> str:
    gs_text = extract_text_range(pdf_path, first_page, last_page, temp_name=temp_name)
    if not extraction_is_weak(gs_text, min_chars=min_chars, min_words=min_words):
        return gs_text

    ocr_text = ocr_extract_text_range(pdf_path, first_page, last_page, temp_name=temp_name)
    if ocr_text and not extraction_is_weak(
        ocr_text,
        min_chars=max(220, min_chars // 2),
        min_words=max(35, min_words // 2),
    ):
        return ocr_text
    return ocr_text or gs_text


def is_review_entry(entry: dict) -> bool:
    section_norm = normalized_letters(entry.get('section', ''))
    title_norm = normalized_letters(entry.get('title', ''))

    if any(token in section_norm for token in ('recenzii', 'bookreviews', 'bookreview')):
        return True

    title = entry.get('title', '')
    if title.count(',') >= 2 and re.search(r'\([^)]{3,80}\)\s*$', title):
        if any(token in title_norm for token in ('editura', 'press', 'volume', 'isbn', 'vienna', 'bucuresti', 'clujnapoca')):
            return True

    return False


def parse_frontmatter(front_text: str, entry: dict) -> dict:
    raw_lines = [clean_line(line) for line in front_text.splitlines()]
    lines = [line for line in raw_lines if line]
    lines = strip_noise_lines(lines)

    review = is_review_entry(entry)

    title = entry['title']
    toc_author = normalize_person_line(entry.get('author', ''))
    title_idx = -1
    for idx, line in enumerate(lines[:20]):
        if line_matches_title(line, title):
            title_idx = idx
            break

    # Author and title are sourced from TOC only (user requirement).
    authors = toc_author or 'N/A'

    affiliation = ''
    for line in lines:
        if re.match(r'^[\*\u2217]\s*', line):
            candidate = re.sub(r'^[\*\u2217]\s*', '', line).strip()
            if len(candidate) > 8:
                affiliation = candidate
                break
    if not affiliation:
        match = re.search(r'(Institutul[^\n]{8,220}?(?:Cluj-Napoca|București|Bucuresti|Timișoara|Timisoara|Iași|Iasi|Sibiu)[^\n]{0,120})', front_text, re.IGNORECASE)
        if match:
            affiliation = clean_line(match.group(1))

    keywords_en = extract_keywords_field(lines, labels=('keywords', 'keyword'))
    keywords_ro = extract_keywords_field(lines, labels=('cuvintecheie',))

    abstract_en = extract_labeled_field(
        lines,
        labels=('abstract',),
        stop_terms=('keywords', 'keyword', 'cuvintecheie', 'rezumat', 'institutul', 'anuarul'),
        max_lines=28,
        max_chars=3000,
    )

    if not abstract_en:
        for idx, line in enumerate(lines[:24]):
            if 'abstract' in normalized_letters(line) and '(' in line:
                abstract_en = collect_block(
                    lines,
                    idx + 1,
                    stop_terms=('keywords', 'keyword', 'cuvintecheie', 'rezumat', 'institutul', 'anuarul'),
                    max_lines=30,
                    max_chars=3200,
                )
                if abstract_en:
                    break

    abstract_ro = extract_labeled_field(
        lines,
        labels=('rezumat',),
        stop_terms=('keywords', 'keyword', 'cuvintecheie', 'abstract', 'institutul', 'anuarul'),
        max_lines=28,
        max_chars=3000,
    )

    if not review and not abstract_ro and not abstract_en:
        start = title_idx + 2 if title_idx >= 0 else 0
        for idx in range(start, min(len(lines), start + 14)):
            line = lines[idx]
            norm = normalized_letters(line)
            if any(token in norm for token in ('keywords', 'keyword', 'cuvintecheie', 'rezumat', 'abstract', 'institutul')):
                continue
            if len(line) >= 120 and not is_upperish(line):
                fallback = collect_block(
                    lines,
                    idx,
                    stop_terms=('keywords', 'keyword', 'cuvintecheie', 'rezumat', 'abstract', 'institutul', 'anuarul'),
                    max_lines=18,
                    max_chars=2200,
                )
                if fallback:
                    if detect_language(title) == 'ro':
                        abstract_ro = fallback
                    else:
                        abstract_en = fallback
                    break

    doi = extract_doi_field(front_text)
    emails = extract_emails_field(front_text)

    if review:
        abstract_ro = ''
        abstract_en = ''
        keywords_ro = ''
        keywords_en = ''
        doi = ''
        emails = ''
    else:
        abstract_ro = sanitize_abstract_text(abstract_ro, lang_hint='ro')
        abstract_en = sanitize_abstract_text(abstract_en, lang_hint='en')

    if not affiliation:
        affiliation = DEFAULT_AFFILIATION

    language = detect_language(title, abstract_en=abstract_en, keywords_en=keywords_en)

    return {
        'title': title,
        'authors': authors,
        'affiliation': affiliation,
        'abstract_ro': abstract_ro,
        'abstract_en': abstract_en,
        'keywords_ro': keywords_ro,
        'keywords_en': keywords_en,
        'doi': doi,
        'emails': emails,
        'language': language,
        'is_review': review,
    }


def build_article_md(entry: dict, frontmatter: dict, issue_meta: dict, full_text: str) -> str:
    lines = [
        f"# {entry['title']}",
        '',
        f"- Autor(i): {frontmatter.get('authors', 'N/A')}",
        f"- Secțiune TOC: {entry.get('section', '') or 'N/A'}",
        f"- Pagini: p. {entry['start_page']}–{entry['end_page']}",
        f"- Afiliere: {frontmatter.get('affiliation', DEFAULT_AFFILIATION)}",
        f"- Email: {frontmatter.get('emails', '') or 'N/A'}",
        f"- DOI: {frontmatter.get('doi', '') or 'N/A'}",
        f"- Limbă: {frontmatter.get('language', 'ro')}",
        f"- Tip intrare: {'recenzie' if frontmatter.get('is_review') else 'articol'}",
        f"- Număr: Vol. {issue_meta.get('volume', '')} Nr. {issue_meta.get('number', '')} ({issue_meta.get('year', '')})",
        '',
        '## Abstract RO',
        frontmatter.get('abstract_ro', '') or '_Nedetectat_',
        '',
        '## Cuvinte-cheie RO',
        frontmatter.get('keywords_ro', '') or '_Nedetectate_',
        '',
        '## Abstract EN',
        frontmatter.get('abstract_en', '') or '_Not detected_',
        '',
        '## Keywords EN',
        frontmatter.get('keywords_en', '') or '_Not detected_',
        '',
        '## Text extras din PDF',
        full_text or '_Text indisponibil_',
        '',
    ]
    return '\n'.join(lines)


def build_issue(issue_input: dict) -> tuple[dict, list[dict]]:
    issue_dir = OUT_ROOT / issue_input['slug']
    src_dir = issue_dir / 'source'
    meta_dir = issue_dir / 'metadata'
    articles_dir = issue_dir / 'articles'
    md_dir = issue_dir / 'md'
    cover_dir = issue_dir / 'cover'

    src_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    articles_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    src_pdf = issue_input['src_pdf']
    local_pdf = src_dir / 'issue.pdf'
    if not local_pdf.exists() or local_pdf.stat().st_size != src_pdf.stat().st_size:
        shutil.copy2(src_pdf, local_pdf)

    toc_txt = meta_dir / 'toc_raw.txt'
    gs_extract_text(local_pdf, toc_txt, 1, 60)
    toc_text = toc_txt.read_text(errors='ignore')

    entries = parse_toc_entries(toc_text)
    page_count = gs_page_count(local_pdf)
    offset = find_offset(local_pdf, entries[0] if entries else None)

    issue_meta = {
        'id': str(issue_input['id']),
        'slug': issue_input['slug'],
        'year': issue_input['year'],
        'volume': issue_input['volume'],
        'number': issue_input['number'],
        'date_published': issue_input['date_published'],
        'title': issue_input['title'],
        'status': 'published',
        'article_count': 0,
        'pages': page_count,
        'doi_prefix': '',
        'publisher': 'Academia Română – Filiala Cluj-Napoca · Institutul „Arhiva de Folclor a Academiei Române”',
        'issn': '1220-3661',
        'issue_pdf_path': f"ingest/issues/{issue_input['slug']}/source/issue.pdf",
        'cover_hint_path': f"ingest/issues/{issue_input['slug']}/cover/",
        'page_offset': offset,
    }

    processed: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        start_printed = int(entry['start_page'])
        next_start = entries[idx]['start_page'] if idx < len(entries) else (page_count - offset + 1)
        end_printed = max(start_printed, int(next_start) - 1)

        start_pdf = max(1, start_printed + offset)
        end_pdf = min(page_count, end_printed + offset)
        if end_pdf < start_pdf:
            continue

        title_slug = slugify(entry['title'])
        article_rel = f"ingest/issues/{issue_input['slug']}/articles/{idx:03d}-{title_slug}.pdf"
        article_abs = ROOT / article_rel
        split_article_pdf(local_pdf, article_abs, start_pdf, end_pdf)

        article_page_count = max(1, end_pdf - start_pdf + 1)
        # Extract from opening page(s) for metadata.
        front_last = min(2, article_page_count)

        front_text = extract_text_best_effort(
            article_abs,
            1,
            front_last,
            temp_name=f"{issue_input['slug']}-{idx:03d}-front.txt",
            min_chars=120,
            min_words=20,
        )
        full_text_raw = extract_text_best_effort(
            article_abs,
            1,
            article_page_count,
            temp_name=f"{issue_input['slug']}-{idx:03d}-full.txt",
            min_chars=max(300, article_page_count * 90),
            min_words=max(50, article_page_count * 22),
        )
        full_text = normalize_full_text(full_text_raw)

        entry_with_pages = {
            **entry,
            'start_page': start_printed,
            'end_page': end_printed,
        }
        parsed = parse_frontmatter(front_text, entry_with_pages)

        md_rel = f"ingest/issues/{issue_input['slug']}/md/{idx:03d}-{title_slug}.md"
        md_abs = ROOT / md_rel
        md_abs.parent.mkdir(parents=True, exist_ok=True)
        md_abs.write_text(build_article_md(entry_with_pages, parsed, issue_meta, full_text), encoding='utf-8')

        processed.append(
            {
                'index': idx,
                'section': entry.get('section', ''),
                'title': entry['title'],
                'author': entry.get('author', ''),
                'authors': parsed['authors'],
                'affiliation': parsed['affiliation'],
                'emails': parsed['emails'],
                'doi': parsed['doi'],
                'language': parsed['language'],
                'is_review': bool(parsed['is_review']),
                'abstract_ro': parsed['abstract_ro'],
                'abstract_en': parsed['abstract_en'],
                'keywords_ro': parsed['keywords_ro'],
                'keywords_en': parsed['keywords_en'],
                'start_page': start_printed,
                'end_page': end_printed,
                'start_pdf_page': start_pdf,
                'end_pdf_page': end_pdf,
                'pdf_path': article_rel,
                'md_path': md_rel,
            }
        )

    issue_meta['article_count'] = len(processed)

    (cover_dir / 'README.txt').write_text(
        'Adaugă aici coperta numărului, de exemplu: cover.jpg sau cover.png\n',
        encoding='utf-8',
    )

    (meta_dir / 'issue.json').write_text(json.dumps(issue_meta, ensure_ascii=False, indent=2), encoding='utf-8')
    (meta_dir / 'article_ranges.json').write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding='utf-8')

    (issue_dir / 'README.md').write_text(
        '\n'.join(
            [
                f"# {issue_input['title']}",
                '',
                f"- An: {issue_input['year']}",
                f"- Volum: {issue_input['volume']}",
                f"- Număr: {issue_input['number']}",
                f"- Pagini totale PDF: {page_count}",
                f"- Articole detectate: {len(processed)}",
                '- PDF sursă: source/issue.pdf',
                '- Copertă: adaugă manual în cover/',
                '',
                'Structură:',
                '- source/: PDF număr complet',
                '- metadata/: TOC brut + metadate + intervale',
                '- articles/: PDF separat per articol',
                '- md/: fișiere Markdown per articol',
                '- cover/: folder pentru imaginea de copertă',
            ]
        ),
        encoding='utf-8',
    )

    return issue_meta, processed


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)

    all_issues = []
    all_articles = []
    article_id = 1

    for issue_input in ISSUES_INPUT:
        issue_meta, entries = build_issue(issue_input)
        all_issues.append(issue_meta)

        for entry in entries:
            all_articles.append(
                {
                    'id': str(article_id),
                    'issue_id': str(issue_input['id']),
                    'title': entry['title'],
                    'authors': entry['authors'] or entry['author'] or 'N/A',
                    'affiliations': entry['affiliation'] or DEFAULT_AFFILIATION,
                    'emails': entry.get('emails', ''),
                    'abstract_ro': entry['abstract_ro'] if not entry['is_review'] else '',
                    'abstract_en': entry['abstract_en'] if not entry['is_review'] else '',
                    'keywords_ro': entry['keywords_ro'] if not entry['is_review'] else '',
                    'keywords_en': entry['keywords_en'] if not entry['is_review'] else '',
                    'pages_start': str(entry['start_page']),
                    'pages_end': str(entry['end_page']),
                    'doi': entry.get('doi', '') if not entry['is_review'] else '',
                    'language': entry['language'],
                    'status': 'published',
                    'conf_title': '0.99',
                    'conf_authors': '0.94',
                    'conf_keywords_ro': '0.90' if entry['keywords_ro'] else '0.35',
                    'conf_keywords_en': '0.90' if entry['keywords_en'] else '0.35',
                    'conf_abstract': '0.90' if (entry['abstract_ro'] or entry['abstract_en']) else '0.30',
                    'pdf_path': entry['pdf_path'],
                    'md_path': entry['md_path'],
                    'section': entry.get('section', ''),
                    'is_review': bool(entry['is_review']),
                }
            )
            article_id += 1

    manifest = {
        'journal': {
            'name': 'Anuarul Arhivei de Folclor / The Folklore Archive Yearbook',
            'abbr': 'AAF',
            'issn': '1220-3661',
            'eissn': '1220-3661',
            'publisher': 'Academia Română – Filiala Cluj-Napoca · Institutul „Arhiva de Folclor a Academiei Române”',
            'country': 'România',
            'language': 'ro',
            'url': 'https://www.iafar.ro',
            'description': 'Publicație științifică a Academiei Române – Filiala Cluj-Napoca, Institutul „Arhiva de Folclor a Academiei Române”. Contact: str. Republicii nr. 59, 400015 Cluj-Napoca · Tel/Fax +40-264-591864 · Email: anuar@iafar.ro.',
        },
        'issues': all_issues,
        'articles': all_articles,
        'generated_at': datetime.datetime.now().isoformat(),
    }

    manifest_json_path = ROOT / 'ingest' / 'issues_manifest.json'
    manifest_js_path = ROOT / 'ingest' / 'issues_manifest.js'
    manifest_json_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest_js_path.write_text('window.__INGEST_MANIFEST = ' + json.dumps(manifest, ensure_ascii=False) + ';\n', encoding='utf-8')

    print(f'Generated: {manifest_json_path}')
    print(f"Issues: {len(all_issues)} | Articles: {len(all_articles)}")


if __name__ == '__main__':
    main()
