from ingest.metadata import parse_frontmatter


def test_parse_frontmatter_extracts_affiliation_abstract_keywords_and_confidence():
    front_text = """
    CERCETĂRILE ETNOLOGICE ZONALE LA CLUJ
    Ion CUCEU*
    The Folklore Archive and the Regional Ethnological Research Programme (Abstract)
    In 2003-2004, the author initiated a regional ethnographic research programme.
    Keywords: folklore archive, ethnology, fieldwork
    Cuvinte-cheie: arhiva de folclor, etnologie
    * Institutul „Arhiva de Folclor a Academiei Române”, Cluj-Napoca.
    """

    entry = {
        "title": "CERCETĂRILE ETNOLOGICE ZONALE LA CLUJ",
        "author": "Ion Cuceu",
        "section": "Studii și cercetări",
        "start_page": 17,
        "end_page": 28,
    }

    parsed = parse_frontmatter(
        front_text=front_text,
        first_page_text=front_text,
        full_text=front_text,
        entry=entry,
        keyword_stopwords={"the", "and", "of"},
        text_quality=0.91,
    )

    assert parsed["authors"] == "Ion Cuceu"
    assert "Institutul" in parsed["affiliation"]
    assert parsed["abstract_en"].endswith(".")
    assert "folklore archive" in parsed["keywords_en"].lower()
    assert parsed["conf_title"] >= 0.9


def test_parse_frontmatter_review_clears_abstract_keywords_and_doi():
    front_text = """
    Macarie ..., 329 p. (Theodor Constantiniu)
    doi:10.1234/abc
    Keywords: should, disappear
    """

    entry = {
        "title": "Macarie ..., 329 p. (Theodor Constantiniu)",
        "author": "Theodor Constantiniu",
        "section": "Recenzii",
        "start_page": 312,
        "end_page": 313,
    }

    parsed = parse_frontmatter(
        front_text=front_text,
        first_page_text=front_text,
        full_text=front_text,
        entry=entry,
        keyword_stopwords=set(),
        text_quality=0.8,
    )

    assert parsed["is_review"] is True
    assert parsed["abstract_en"] == ""
    assert parsed["keywords_en"] == ""
    assert parsed["doi"] == ""


def test_parse_frontmatter_enforces_abstract_when_keywords_exist():
    front_text = """
    TITLU STUDIU
    ION POP
    Keywords: arhivă, etnologie
    Cuvinte-cheie: arhivă, etnologie
    """
    full_text = """
    TITLU STUDIU

    Acest studiu prezintă metodologia cercetării de teren și rezultatele principale obținute în arhivele etnografice din Transilvania.
    Sunt discutate sursele, limitele și contribuțiile teoretice.
    """
    entry = {
        "title": "TITLU STUDIU",
        "author": "Ion Pop",
        "section": "Studii și cercetări",
        "start_page": 10,
        "end_page": 20,
    }

    parsed = parse_frontmatter(
        front_text=front_text,
        first_page_text=front_text,
        full_text=full_text,
        entry=entry,
        keyword_stopwords=set(),
        text_quality=0.8,
    )

    assert parsed["keywords_en"] != ""
    assert parsed["abstract_en"] != ""


def test_keywords_are_not_derived_from_random_text_without_label():
    front_text = """
    TITLU STUDIU
    ION POP
    Acest paragraf are termeni precum etnologie, arhivă, metodologie dar nu este linie de keywords.
    """
    entry = {
        "title": "TITLU STUDIU",
        "author": "Ion Pop",
        "section": "Studii și cercetări",
        "start_page": 10,
        "end_page": 20,
    }

    parsed = parse_frontmatter(
        front_text=front_text,
        first_page_text=front_text,
        full_text=front_text,
        entry=entry,
        keyword_stopwords=set(),
        text_quality=0.8,
    )

    assert parsed["keywords_en"] == ""
    assert parsed["keywords_ro"] == ""


def test_keywords_ignore_sentence_like_continuation_after_label():
    front_text = """
    TITLU STUDIU
    ION POP
    Keywords: etnologie, arhivă, teren.
    Acest paragraf descrie metodologia și nu trebuie inclus la keywords.
    """
    entry = {
        "title": "TITLU STUDIU",
        "author": "Ion Pop",
        "section": "Studii și cercetări",
        "start_page": 10,
        "end_page": 20,
    }

    parsed = parse_frontmatter(
        front_text=front_text,
        first_page_text=front_text,
        full_text=front_text,
        entry=entry,
        keyword_stopwords=set(),
        text_quality=0.8,
    )

    assert "metodologia" not in parsed["keywords_en"].lower()
    assert parsed["keywords_en"].lower().startswith("etnologie, arhivă, teren")
