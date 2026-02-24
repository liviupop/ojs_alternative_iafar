from ingest.series1 import (
    TocEntry,
    SummaryEntry,
    _extract_page_only_token,
    extract_keywords_fr,
    match_toc_with_summaries,
    parse_summary_entries,
    parse_toc_entries,
    translate_keywords_to_ro,
)


def test_parse_toc_entries_series1_basic():
    toc_text = """
    CUPRINSUL
    PAG.
    ION MUȘLEA, Academia Română și folclorul 1
    ARTUR GOROVEI, „Șezătoarea”. Povestea vieții unei reviste de folclor 9
    Bibliografia folclorului românesc pe anul 1930 241
    Raport anual 251
    RÉSUMÉ DES ARTICLES 253
    """
    entries = parse_toc_entries(toc_text)
    assert len(entries) == 4
    assert entries[0].author == "Ion Mușlea"
    assert entries[0].title.startswith("Academia Română")
    assert entries[0].page_start == 1
    assert entries[1].page_start == 9
    assert entries[0].page_end == 8


def test_parse_summary_entries_with_page_ranges():
    summary_text = """
    RÉSUMÉ DES ARTICLES
    ION MUȘLEA, L'Académie Roumaine et le folklore (p. 1—7). Bref résumé en français.
    ARTUR GOROVEI, Histoire d'une revue de folklore (p. 9—39). Deuxième résumé.
    Bibliographie du folklore roumain (p. 241—249).
    """
    parsed = parse_summary_entries(summary_text, summary_start_page_pdf=255)
    assert len(parsed) >= 2
    assert parsed[0].author == "Ion Mușlea"
    assert parsed[0].page_start == 1
    assert parsed[0].page_end == 7
    assert "Bref résumé" in parsed[0].abstract_fr


def test_match_toc_to_summaries_prefers_page_match():
    toc = [
        TocEntry(1, "", "Ion Mușlea", "Academia Română și folclorul", "1", 1, 7),
        TocEntry(2, "", "Artur Gorovei", "Șezătoarea", "9", 9, 39),
    ]
    summaries = [
        SummaryEntry("Ion Mușlea", "L'Académie Roumaine et le folklore", 1, 7, "Rezumat 1.", 255),
        SummaryEntry("Artur Gorovei", "Histoire d'une revue", 9, 39, "Rezumat 2.", 255),
    ]
    matched = match_toc_with_summaries(toc, summaries)
    assert matched[1].page_start == 1
    assert matched[2].page_start == 9


def test_keywords_fr_and_ro_translation():
    abstract_fr = (
        "L'article présente la littérature populaire, les chansons et les coutumes "
        "dans les villages roumains."
    )
    keywords_fr = extract_keywords_fr(abstract_fr, size=5)
    keywords_ro = translate_keywords_to_ro(keywords_fr)
    assert len(keywords_fr) <= 5
    assert len(keywords_ro) <= 5


def test_extract_page_only_ignores_year_ranges():
    assert _extract_page_only_token("1871—1907") is None
    assert _extract_page_only_token("1 0 7 -") == "107"


def test_parse_toc_splits_when_new_author_starts_before_page():
    toc_text = """
    CUPRINSUL
    TRAIAN GERMAN, Tovărășiile de Crăciun ale feciorilor români din
    Ardeal
    ION BREAZU, Versuri populare în manuscrise ardelene vechi 79
    """
    entries = parse_toc_entries(toc_text)
    assert len(entries) == 2
    assert entries[0].author == "Traian German"
    assert entries[0].page_start is None
    assert entries[1].author == "Ion Breazu"
    assert entries[1].page_start == 79
