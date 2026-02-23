# Skill: Segmentare issue in articole (multi-model)

Acest skill se trimite identic catre OpenAI, Anthropic si Google pentru rezultate consistente.

## Obiectiv
Transforma un text brut de issue (TOC + rezumate) in lista structurata de articole.

## Reguli
1. Pastreaza ordinea articolelor dupa pagini.
2. Nu inventa informatii lipsa.
3. Normalizeaza autorii in sir separat prin virgula.
4. Extrage separat `abstract_ro` / `abstract_en`.
5. Extrage separat `keywords_ro` / `keywords_en`.
6. Returneaza strict JSON valid, fara explicatii.

## Contract JSON
```json
{
  "articles": [
    {
      "title": "string",
      "authors": "string",
      "affiliations": "string",
      "emails": "string",
      "abstract_ro": "string",
      "abstract_en": "string",
      "keywords_ro": "string",
      "keywords_en": "string",
      "pages_start": "string",
      "pages_end": "string",
      "doi": "string",
      "language": "string"
    }
  ]
}
```
