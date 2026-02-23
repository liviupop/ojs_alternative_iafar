# Skill Update v2: Segmentare issue academic (multi-model, TOC-first)

Acest skill se transmite identic către OpenAI / Anthropic / Google.
Scopul este consistență de output și eliminarea variațiilor dintre modele.

## Obiectiv
Transformă un issue PDF (TOC + pagini articol) în date curate pentru:
- TOC public cu secțiuni
- pagină de articol (autori, afiliere, abstract, keywords, pagini)
- fișiere `.md` per articol pentru indexare LLM

## Input minim
- `toc_text`: text extras din Cuprins
- `article_front_text`: primele 1-3 pagini ale articolului
- `article_full_text`: text integral articol (opțional, pentru `.md`)
- `issue_meta`: volum/număr/an

## Reguli obligatorii
1. Respectă TOC-ul exact.
- Nu schimba ordinea intrărilor.
- Nu combina articole diferite.
- Nu muta articole între secțiuni.

2. Include secțiunile în output TOC.
- Exemple: `ARHIVA...`, `STUDII ȘI CERCETĂRI`, `NOTE DE LECTURĂ`, `RECENZII`.
- Fiecare articol primește `section`.

3. Decuparea paginilor se face strict după TOC.
- `pages_start` / `pages_end` vin din TOC, nu estimate semantic.

4. Extragere metadate pentru articole non-review.
- `title`
- `authors`
- `affiliations` (ex: `* Institutul ...`)
- `abstract_en` (extras din prima pagină; fără câmp separat `abstract_ro`)
- `keywords_ro` / `keywords_en` cu aceeași listă unificată (RO + EN)
- `pages_start` / `pages_end`

5. Recenziile se tratează separat.
- Dacă `section` = recenzii/book reviews sau intrarea este clar recenzie:
  - `is_review = true`
  - `abstract_en = ""`
  - `keywords_ro = ""`
  - `keywords_en = ""`

6. Fără invenții.
- Dacă un câmp nu există clar în text, returnează `""`.
- Nu inventa DOI, email, afiliere, abstract, keywords.

7. Curățare text controlată.
- Păstrează diacriticele dacă sunt lizibile.
- Elimină doar zgomotul evident de OCR (spații duble, control chars).
- Nu rescrie academic stilistic conținutul.

8. Normalizează autorii fără a pierde sensul.
- `Ion CUCEU*` -> `Ion Cuceu`
- Elimină markerii `*`, `1`, etc. din nume.

9. Keywords: scurte, fără paragraf.
- Oprește extragerea la finalul propoziției de keywords.
- Nu include paragraful următor în keywords.
- Dacă ultimul keyword lipsește sau e corupt OCR, completează-l din abstract sau din textul articolului (termen scurt, relevant).

10. Contract JSON strict.
- Returnează doar JSON valid, fără explicații.

## Contract JSON
```json
{
  "toc": {
    "sections": [
      {
        "name": "string",
        "order": 1
      }
    ],
    "entries": [
      {
        "section": "string",
        "title": "string",
        "authors": "string",
        "pages_start": "string",
        "pages_end": "string",
        "is_review": false
      }
    ]
  },
  "articles": [
    {
      "title": "string",
      "authors": "string",
      "affiliations": "string",
      "emails": "string",
      "abstract_en": "string",
      "keywords_ro": "string",
      "keywords_en": "string",
      "pages_start": "string",
      "pages_end": "string",
      "language": "ro|en|de|fr",
      "section": "string",
      "is_review": false,
      "md_content": "string"
    }
  ]
}
```

## Criterii QA
- Toate intrările din TOC au `pages_start` și `pages_end`.
- `is_review=true` nu are abstract/keywords.
- Ordinea articolelor este identică cu TOC.
- `md_content` include titlu, autori, pagini, abstract/keywords (dacă există), text extras.

## Prompt scurt recomandat (identic pentru toate modelele)
"Extrage TOC cu secțiuni și articole în ordinea exactă a paginilor. Pentru articole non-review extrage autori, afiliere, abstract și keywords din primele pagini. Pentru recenzii setează abstract/keywords goale. Nu inventa date. Returnează strict JSON conform contractului."
