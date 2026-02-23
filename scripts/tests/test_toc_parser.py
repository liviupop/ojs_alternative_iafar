from ingest.toc_parser import parse_toc_entries


def test_parse_toc_entries_accepts_non_roman_sections_and_short_titles():
    toc = """
    COPERTA
    CUPRINS
    STUDII SI CERCETARI
    ION TALOȘ
    Prefață 7
    ANAMARIA LISOVSCHI
    De-ale carnavalului 83
    RECENZII
    Macarie ..., 329 p. (Theodor Constantiniu) 312
    CONTENTS
    """

    entries = parse_toc_entries(toc)
    assert len(entries) == 3
    assert entries[0]["title"] == "Prefață"
    assert entries[0]["author"] == "Ion Taloș"
    assert entries[2]["author"] == "Theodor Constantiniu"
