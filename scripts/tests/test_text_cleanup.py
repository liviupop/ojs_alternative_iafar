from ingest.text_cleanup import (
    enforce_last_keyword_from_context,
    ligature_repair,
    sanitize_abstract_text,
)


def test_ligature_repair_dictionary_and_splits():
    src = "inuential gure oers eldwork ourish speci c de ned"
    out = ligature_repair(src)
    assert "influential" in out.lower()
    assert "figure" in out.lower()
    assert "offers" in out.lower()
    assert "fieldwork" in out.lower()
    assert "flourish" in out.lower()
    assert "specific" in out.lower()
    assert "defined" in out.lower()


def test_sanitize_abstract_repairs_missing_the_and_terminal_period():
    src = "□e paper analyzes rst-stage ndings"
    out = sanitize_abstract_text(src, lang_hint="en")
    assert out.startswith("The paper")
    assert "first-stage" in out or "first stage" in out
    assert out.endswith(".")


def test_enforce_last_keyword_from_context_replaces_missing_term():
    keywords = "etnologie, folclor, invalidkeyword"
    abstract = "Acest studiu despre arhiva include corpus folcloric regional."
    result = enforce_last_keyword_from_context(
        keywords,
        abstract,
        "",
        stopwords={"acest", "studiu", "despre"},
    )
    assert "invalidkeyword" not in result
