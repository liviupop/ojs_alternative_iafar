from ingest.language import detect_language


def test_detect_language_romanian_body():
    body = "Acest articol prezintă o analiză etnografică asupra comunităților rurale din Transilvania."
    assert detect_language(title="Analiză etnografică", body_text=body) == "ro"


def test_detect_language_english_body():
    body = "This article presents a comparative study of rural folklore archives and fieldwork methods."
    assert detect_language(title="Comparative study", body_text=body) == "en"


def test_detect_language_french_fallback():
    assert detect_language(title="Résumé de recherche", body_text="", abstract_en="", keywords_en="les traditions") == "fr"
