# Ingest scripts

## build_ingest_library.py
Construiește biblioteca de ingest pentru numerele AAF din PDF-urile sursă.

Ce face:
- citește TOC din segmentul `CUPRINS ... CONTENTS/SOMMARIO/INHALT`
- parsează intrările în ordinea din Cuprins (inclusiv recenzii)
- taie PDF-ul pe intervalele detectate cu **PyMuPDF**
- folosește TOC ca sursă de adevăr pentru `title` și `authors`
- extrage metadatele din primele pagini (afiliere, abstract, keywords)
- folosește OCR fallback cu Tesseract (`ron+eng+deu+fra`, 300 DPI)
- generează `md` per articol în `ingest/issues/<slug>/md/`
- generează `ingest/issues_manifest.json` și `ingest/issues_manifest.js`
- scrie confidence scores reale pe baza calității textului extras

Rulare:
```bash
python3 scripts/build_ingest_library.py
```

Opțiuni utile:
```bash
python3 scripts/build_ingest_library.py --issue aaf-xxix-2025 --log-level DEBUG
python3 scripts/build_ingest_library.py --source-root "/cale/catre/pdf-uri"
```

Teste:
```bash
pytest -q scripts/tests
```

Dependințe:
```bash
pip install -r scripts/requirements.txt
```

Notă:
- Pentru copertă, adaugă manual fișierul în `ingest/issues/<slug>/cover/` (ex: `cover.jpg`).
