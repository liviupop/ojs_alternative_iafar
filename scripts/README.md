# Ingest scripts

## build_ingest_library.py
Construiește biblioteca de ingest pentru numerele AAF din PDF-urile sursă.

Ce face:
- citește TOC strict din segmentul `CUPRINS ... CONTENTS/SOMMARIO/INHALT`
- extrage intrările în ordinea din Cuprins (inclusiv secțiuni de recenzii)
- taie PDF-ul pe intervalele de pagini detectate din TOC
- creează structura pe număr în `ingest/issues/<slug>/`
- generează `ingest/issues_manifest.json` și `ingest/issues_manifest.js`

Rulare:
```bash
python3 scripts/build_ingest_library.py
```

Notă:
- Scriptul folosește Ghostscript (`/opt/homebrew/bin/gs`).
- Pentru copertă, adaugă manual fișierul în `ingest/issues/<slug>/cover/` (ex: `cover.jpg`).
