#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path('/Users/liviupop/Downloads/ojs_alternative_iafar')
SOURCE_ROOT = Path('/Users/liviupop/Downloads/Anuarul Arhivei de Folclor (arhiva)')
OUT_ROOT = ROOT / 'ingest' / 'issues'
TMP_ROOT = ROOT / 'tmp' / 'pdfs' / 'ingest'

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


def sh(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def gs_extract_text(pdf_path: Path, out_txt: Path, first: int, last: int):
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        '/opt/homebrew/bin/gs', '-q', '-sDEVICE=txtwrite',
        f'-dFirstPage={first}', f'-dLastPage={last}',
        '-o', str(out_txt), str(pdf_path),
    ]
    subprocess.run(cmd, check=True)


def gs_page_count(pdf_path: Path) -> int:
    cmd = [
        '/opt/homebrew/bin/gs', '-q', '-sDEVICE=txtwrite',
        '-dFirstPage=99999', '-dLastPage=99999',
        '-o', '/tmp/ignore-gs-pagecount.txt', str(pdf_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    msg = (proc.stdout or '') + '\n' + (proc.stderr or '')
    m = re.search(r'number of pages in the file:\s*(\d+)', msg)
    if not m:
        raise RuntimeError(f'Cannot detect page count for {pdf_path}')
    return int(m.group(1))


def clean_line(s: str) -> str:
    s = s.replace('\u00a0', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalized_letters(s: str) -> str:
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^a-z]+', '', s.lower())


def normalize_text(s: str) -> str:
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def is_upperish(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    up = sum(1 for c in letters if c.isupper())
    return (up / len(letters)) > 0.82


def parse_toc_entries(toc_text: str):
    lines = [clean_line(line) for line in toc_text.splitlines()]
    start = next((i for i, line in enumerate(lines) if 'cuprins' in normalized_letters(line)), None)
    if start is None:
        return []
    end = next((
        i for i, line in enumerate(lines[start + 1:], start + 1)
        if any(token in normalized_letters(line) for token in ('contents', 'sommario', 'sommaire', 'inhalt'))
    ), len(lines))
    toc = lines[start + 1:end]

    entries = []
    current_author = ''
    pending = []
    for line in toc:
        if not line:
            continue
        if re.match(r'^[IVXLCM]+\.?\s', line):
            pending = []
            continue

        m = re.match(r'^(.*?)(\d{1,4})\s*$', line)
        if m:
            title = clean_line(m.group(1))
            page = int(m.group(2))
            if pending:
                title = clean_line(' '.join(pending + [title]))
                pending = []
            if len(title) >= 8 and not is_upperish(title):
                entries.append({'author': current_author, 'title': title, 'start_page': page})
            continue

        if is_upperish(line) and len(line) <= 140 and not any(ch.isdigit() for ch in line):
            current_author = line.title() if line == line.upper() else line
            pending = []
            continue

        pending.append(line)

    dedup = []
    seen = set()
    for entry in entries:
        key = (entry['start_page'], entry['title'])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(entry)

    dedup.sort(key=lambda item: item['start_page'])
    return dedup


def detect_language(title: str) -> str:
    lower = title.lower()
    if any(token in lower for token in ['zur ', 'deutsch', 'über ']):
        return 'de'
    if any(token in lower for token in ['the ', ' and ', ' in memoriam', 'journal', 'contents']):
        return 'en'
    return 'ro'


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:120] or 'articol'


def find_offset(pdf_path: Path, first_entry):
    if not first_entry:
        return 0
    needle = normalize_text(first_entry['title'])[:50]
    printed = int(first_entry['start_page'])
    tmp_page = TMP_ROOT / 'single-page.txt'
    hits = []
    upper = min(130, printed + 70)

    for page in range(1, upper + 1):
        gs_extract_text(pdf_path, tmp_page, page, page)
        text = normalize_text(tmp_page.read_text(errors='ignore'))
        if needle and needle in text:
            hits.append(page)

    candidates = [page for page in hits if page >= printed]
    if candidates:
        return candidates[0] - printed
    return 0


def split_article_pdf(src_pdf: Path, out_pdf: Path, first_page: int, last_page: int):
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        '/opt/homebrew/bin/gs', '-q', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
        f'-dFirstPage={first_page}', f'-dLastPage={last_page}',
        '-o', str(out_pdf), str(src_pdf),
    ]
    subprocess.run(cmd, check=True)


def build_issue(issue_input):
    issue_dir = OUT_ROOT / issue_input['slug']
    src_dir = issue_dir / 'source'
    meta_dir = issue_dir / 'metadata'
    articles_dir = issue_dir / 'articles'
    cover_dir = issue_dir / 'cover'
    src_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    articles_dir.mkdir(parents=True, exist_ok=True)
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

    processed = []
    for i, entry in enumerate(entries):
        start_printed = int(entry['start_page'])
        next_start = entries[i + 1]['start_page'] if i + 1 < len(entries) else (page_count - offset + 1)
        end_printed = max(start_printed, int(next_start) - 1)
        start_pdf = max(1, start_printed + offset)
        end_pdf = min(page_count, end_printed + offset)
        if end_pdf < start_pdf:
            continue

        title_slug = slugify(entry['title'])
        article_rel = f"ingest/issues/{issue_input['slug']}/articles/{i+1:03d}-{title_slug}.pdf"
        out_pdf = ROOT / article_rel
        split_article_pdf(local_pdf, out_pdf, start_pdf, end_pdf)

        processed.append({
            'index': i + 1,
            'author': entry.get('author', ''),
            'title': entry['title'],
            'language': detect_language(entry['title']),
            'start_page': start_printed,
            'end_page': end_printed,
            'start_pdf_page': start_pdf,
            'end_pdf_page': end_pdf,
            'pdf_path': article_rel,
        })

    (cover_dir / 'README.txt').write_text(
        'Adaugă aici coperta numărului, de exemplu: cover.jpg sau cover.png\n',
        encoding='utf-8',
    )

    issue_meta = {
        'id': issue_input['id'],
        'slug': issue_input['slug'],
        'year': issue_input['year'],
        'volume': issue_input['volume'],
        'number': issue_input['number'],
        'date_published': issue_input['date_published'],
        'title': issue_input['title'],
        'status': 'published',
        'article_count': len(processed),
        'pages': page_count,
        'doi_prefix': '10.12345',
        'publisher': 'Academia Română – Filiala Cluj-Napoca · Institutul „Arhiva de Folclor a Academiei Române”',
        'issn': '1220-3661',
        'issue_pdf_path': f"ingest/issues/{issue_input['slug']}/source/issue.pdf",
        'cover_hint_path': f"ingest/issues/{issue_input['slug']}/cover/",
        'page_offset': offset,
    }

    (meta_dir / 'issue.json').write_text(json.dumps(issue_meta, ensure_ascii=False, indent=2), encoding='utf-8')
    (meta_dir / 'article_ranges.json').write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding='utf-8')
    (issue_dir / 'README.md').write_text(
        '\n'.join([
            f"# {issue_input['title']}",
            '',
            f"- An: {issue_input['year']}",
            f"- Volum: {issue_input['volume']}",
            f"- Număr: {issue_input['number']}",
            f"- Pagină totală PDF: {page_count}",
            f"- Articole detectate: {len(processed)}",
            f"- PDF sursă: source/issue.pdf",
            f"- Copertă: adaugă manual în cover/",
            '',
            'Structură:',
            '- source/: PDF număr complet',
            '- metadata/: TOC brut + metadate + intervale',
            '- articles/: PDF separat per articol',
            '- cover/: folder pentru imaginea de copertă',
        ]),
        encoding='utf-8',
    )

    return issue_meta, processed


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)

    all_issues = []
    all_articles = []
    article_id = 1

    for issue_input in ISSUES_INPUT:
        issue_meta, ranges = build_issue(issue_input)
        issue_meta['id'] = str(issue_meta['id'])
        all_issues.append(issue_meta)

        for entry in ranges:
            all_articles.append({
                'id': str(article_id),
                'issue_id': str(issue_input['id']),
                'title': entry['title'],
                'authors': entry['author'] or 'N/A',
                'affiliations': 'Institutul „Arhiva de Folclor a Academiei Române”, Cluj-Napoca',
                'emails': 'anuar@iafar.ro',
                'abstract_ro': '',
                'abstract_en': '',
                'keywords_ro': 'folclor, etnologie',
                'keywords_en': 'folklore, ethnology',
                'pages_start': str(entry['start_page']),
                'pages_end': str(entry['end_page']),
                'doi': '',
                'language': entry['language'],
                'status': 'published',
                'conf_title': '0.99',
                'conf_authors': '0.99',
                'conf_keywords_ro': '0.90',
                'conf_keywords_en': '0.90',
                'conf_abstract': '0.80',
                'pdf_path': entry['pdf_path'],
            })
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
        'generated_at': __import__('datetime').datetime.now().isoformat(),
    }

    manifest_json_path = ROOT / 'ingest' / 'issues_manifest.json'
    manifest_js_path = ROOT / 'ingest' / 'issues_manifest.js'
    manifest_json_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest_js_path.write_text(
        'window.__INGEST_MANIFEST = ' + json.dumps(manifest, ensure_ascii=False) + ';\n',
        encoding='utf-8',
    )

    print(f"Generated: {manifest_json_path}")
    print(f"Issues: {len(all_issues)} | Articles: {len(all_articles)}")


if __name__ == '__main__':
    main()
