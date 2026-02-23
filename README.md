# OJS Alternative IAFAR

Interfață jurnal academic (public + dashboard editorial) cu ingest PDF pe TOC și bibliotecă de articole decupate.

## Ce este inclus în repository
- aplicația principală: `app.html`
- manifest ingest: `ingest/issues_manifest.json`, `ingest/issues_manifest.js`
- articole decupate per număr: `ingest/issues/*/articles/*.pdf`
- metadate TOC și intervale: `ingest/issues/*/metadata/*`
- script ingest: `scripts/build_ingest_library.py`

## Ce NU este inclus
- PDF-urile complete de număr (`ingest/issues/*/source/issue.pdf`) sunt excluse intenționat.

## Rebuild ingest
```bash
python3 scripts/build_ingest_library.py
```

## Copertă număr
Adaugă manual coperta în:
- `ingest/issues/<slug>/cover/cover.jpg` (sau `.jpeg`, `.png`)
