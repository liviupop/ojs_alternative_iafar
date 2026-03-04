#!/usr/bin/env python3
"""
rebuild_series3_toc.py — Rebuild TOC + article_ranges pentru seria 3 (toate 4 numere)

Actualizează:
  - ingest/issues/{slug}/metadata/article_ranges.json  (corecții author/title/section)
  - ingest/issues/{slug}/metadata/toc_entries.json     (nou, creat din zero)

Rulează din root-ul proiectului:
    python3 scripts/rebuild_series3_toc.py [--dry-run]
"""

import json
import sys
import copy
from pathlib import Path

BASE    = Path(__file__).parent.parent   # root proiect
SCRIPTS = Path(__file__).parent

DRY_RUN = "--dry-run" in sys.argv

# ─── NORMALIZARE SECȚIUNI ─────────────────────────────────────────────────────
# Unele numere au secțiunile scrise spaced-out ("R E C E N Z I I").
# Lookup explicit — mai robust decât regex pentru litere singulare vs cuvinte.

SECTION_NORM = {
    "R E C E N Z I I":                       "RECENZII",
    "R E S T I T U I R I":                   "RESTITUIRI",
    "N O T E DE L E C T U R A":              "NOTE DE LECTURA",
    "N O T E DE L E C T U R Ă":             "NOTE DE LECTURĂ",
    "N O T E D E L E C T U R Ă":            "NOTE DE LECTURĂ",
    "S T U D I I  S I  C E R C E T A R I":  "STUDII SI CERCETARI",
    "STUDII ŞI CERCETĂRI":                   "STUDII ȘI CERCETĂRI",
    "STUDII SI CERCETARI":                   "STUDII ȘI CERCETĂRI",
}

def normalize_section(s: str) -> str:
    s = s.strip()
    return SECTION_NORM.get(s, s)


# ─── CORECȚII PUNCTUALE (PATCHES) ─────────────────────────────────────────────
# Format: {art_index: {camp: valoare_corecta, ...}}

PATCHES_2023 = {
    20: {
        # Autori gresit atribuiti lui Zoltan Gergely; titlul continea si autorii
        "author":  "Svetlana Badrajan, Vitalie Grib",
        "authors": "Svetlana Badrajan, Vitalie Grib",
        "title":   (
            "Lidia Severin \u2013 o promotoare a c\u00e2ntecului folcloric "
            "\u00een a doua jum\u0103tate a secolului XX, "
            "\u00eenceputul secolului XXI"
        ),
    },
    49: {
        # Lipsea autorul; titlul continea si numele autorului
        "author":  "Mihai B\u0103rbulescu",
        "authors": "Mihai B\u0103rbulescu",
        "title":   "R\u0103zvan Theodorescu (1939\u20132023)",
    },
}

PATCHES_2024 = {}   # datele par corecte
PATCHES_2025 = {}   # datele par corecte


# ─── FUNCȚII I/O ──────────────────────────────────────────────────────────────

def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data: object):
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if DRY_RUN:
        print(f"  [DRY-RUN] ar scrie {path.relative_to(BASE)} ({len(out)} chars)")
    else:
        path.write_text(out, encoding="utf-8")
        print(f"  OK {path.relative_to(BASE)}")

def article_ranges_path(slug: str) -> Path:
    return BASE / "ingest" / "issues" / slug / "metadata" / "article_ranges.json"

def toc_entries_path(slug: str) -> Path:
    return BASE / "ingest" / "issues" / slug / "metadata" / "toc_entries.json"


# ─── FUNCȚII CORE ─────────────────────────────────────────────────────────────

def apply_patches(data: list, patches: dict) -> list:
    data = copy.deepcopy(data)
    for art in data:
        idx = art.get("index")
        if idx in patches:
            for k, v in patches[idx].items():
                old = art.get(k)
                art[k] = v
                if old != v:
                    print(f"    patch art{idx} [{k}]: {str(old)[:60]!r} -> {str(v)[:60]!r}")
    return data

def normalize_all_sections(data: list) -> list:
    data = copy.deepcopy(data)
    for art in data:
        raw  = art.get("section", "")
        norm = normalize_section(raw)
        if norm != raw:
            print(f"    norm art{art.get('index')} section: {raw!r} -> {norm!r}")
        art["section"] = norm
    return data

def make_toc_entry(art: dict, toc_index: int, file_index: int) -> dict:
    """Construieste un entry TOC din datele unui articol."""
    return {
        "toc_index":  toc_index,
        "file_index": file_index,
        "section":    art.get("section", ""),
        "author":     art.get("author", "") or art.get("authors", ""),
        "title":      art.get("title", ""),
        "start_page": art.get("start_page", 0),
        "end_page":   art.get("end_page", 0),
        "is_review":  art.get("is_review", False),
        "pdf_path":   art.get("pdf_path", ""),
        "md_path":    art.get("md_path", ""),
    }


# ─── PROCESARE 2022 (din toc_data_2022.json) ──────────────────────────────────
# Mapare speciala: fisierul 006 e Sandor Varga (eliminat din TOC).
# TOC 1-5  -> fisier 1-5
# TOC 6-58 -> fisier 7-59  (sar fisierul 6)

def process_2022():
    slug = "aaf-xxv-xxvi-2022"
    print(f"\n{'='*60}")
    print(f"  {slug}")
    print(f"{'='*60}")

    toc_raw = load_json(SCRIPTS / "toc_data_2022.json")
    # Format fiecare row: [toc_idx, section, author, title, start_page, is_review]

    arts_list = load_json(article_ranges_path(slug))
    arts = {a["index"]: copy.deepcopy(a) for a in arts_list}

    def toc_to_file(toc_idx: int) -> int:
        return toc_idx if toc_idx <= 5 else toc_idx + 1

    toc_entries = []

    for row in toc_raw:
        toc_idx, section, author, title, start_page, is_review = row
        file_idx = toc_to_file(toc_idx)

        if file_idx not in arts:
            print(f"  ATENTIE: TOC {toc_idx} -> fisier {file_idx} nu exista in article_ranges!")
            continue

        art = arts[file_idx]

        # Aplica datele din toc_data (sursa de adevar pentru TOC)
        changed_fields = []
        for k, v in [("section", section), ("author", author),
                     ("authors", author), ("title", title),
                     ("start_page", start_page), ("is_review", is_review)]:
            if art.get(k) != v:
                changed_fields.append(k)
                art[k] = v
        if changed_fields:
            print(f"    upd art{file_idx}(toc{toc_idx}): {changed_fields}")

        toc_entries.append(make_toc_entry(art, toc_idx, file_idx))

    # Fisierul 006 (Sandor Varga) — marcat ca eliminat din TOC
    if 6 in arts:
        arts[6]["toc_deleted"] = True
        arts[6]["toc_note"]    = "Eliminat din TOC (misplacement — articol din alt numar)"
        print(f"    art6 marcat toc_deleted=True")

    updated = [arts[i] for i in sorted(arts.keys())]

    write_json(article_ranges_path(slug), updated)
    write_json(toc_entries_path(slug), toc_entries)

    print(f"  -> article_ranges: {len(updated)} (incl. 1 deleted), toc_entries: {len(toc_entries)}")


# ─── PROCESARE 2023, 2024, 2025 ───────────────────────────────────────────────

def process_issue(slug: str, patches: dict):
    print(f"\n{'='*60}")
    print(f"  {slug}")
    print(f"{'='*60}")

    arts = load_json(article_ranges_path(slug))
    arts = apply_patches(arts, patches)
    arts = normalize_all_sections(arts)

    toc_entries = [make_toc_entry(a, a["index"], a["index"]) for a in arts]

    write_json(article_ranges_path(slug), arts)
    write_json(toc_entries_path(slug), toc_entries)

    print(f"  -> article_ranges: {len(arts)}, toc_entries: {len(toc_entries)}")


# ─── VALIDARE ─────────────────────────────────────────────────────────────────

def validate_results():
    """Verifica sumara dupa scriere."""
    print(f"\n{'='*60}")
    print("  VALIDARE")
    print(f"{'='*60}")
    expected = {
        "aaf-xxv-xxvi-2022": (59, 58),   # 59 in article_ranges (1 deleted), 58 in toc
        "aaf-xxvii-2023":    (49, 49),
        "aaf-xxviii-2024":   (24, 24),
        "aaf-xxix-2025":     (29, 29),
    }
    ok = True
    for slug, (exp_ar, exp_toc) in expected.items():
        ar  = load_json(article_ranges_path(slug))
        toc = load_json(toc_entries_path(slug))
        ar_ok  = len(ar)  == exp_ar
        toc_ok = len(toc) == exp_toc
        status = "OK" if (ar_ok and toc_ok) else "EROARE"
        print(f"  {status} {slug}: article_ranges={len(ar)}/{exp_ar} toc_entries={len(toc)}/{exp_toc}")
        if not (ar_ok and toc_ok):
            ok = False
    return ok


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if DRY_RUN:
        print("[DRY-RUN MODE — nu se scrie nimic pe disk]\n")

    process_2022()
    process_issue("aaf-xxvii-2023", PATCHES_2023)
    process_issue("aaf-xxviii-2024", PATCHES_2024)
    process_issue("aaf-xxix-2025",  PATCHES_2025)

    if not DRY_RUN:
        ok = validate_results()
        sys.exit(0 if ok else 1)

    print(f"\nRebuild seria 3 complet.")
