from confluo_scout.records import (
    clean_text,
    dehyphenate,
    label_from_text,
    norm_title,
    parse_score,
    split_authors_bibtex,
)


def test_parse_score_variants():
    assert parse_score(6) == (6.0, "6")
    assert parse_score("6: marginally above the acceptance threshold")[0] == 6.0
    assert parse_score({"value": "3"})[0] == 3.0
    assert parse_score("No ethics review needed.")[0] is None
    assert parse_score(None) == (None, None)


def test_labels():
    assert label_from_text("ICLR 2026 Oral") == ("Oral", 4)
    assert label_from_text("NeurIPS 2026 spotlight") == ("Spotlight", 3)
    assert label_from_text("ICML 2026 regular") == ("Poster", 2)
    assert label_from_text("Accept (Highlight)") == ("Highlight", 3)
    assert label_from_text("Accept") == ("Accepted", 2)
    assert label_from_text("Submitted to ICLR 2027") == (None, None)


def test_title_norm_and_cleaning():
    assert norm_title("Attention Is All You Need!") == norm_title("attention is all you need")
    assert norm_title("Gödel’s <i>Theorem</i>") == "godelstheorem"
    assert clean_text("a &amp; b  <b>c</b>") == "a & b c"
    assert dehyphenate("converting an im- age from one domain") == "converting an image from one domain"
    assert dehyphenate("state- Of the art") == "state- Of the art"


def test_bibtex_authors():
    assert split_authors_bibtex("Yu, Shujian and Jenssen, Robert") == ["Shujian Yu", "Robert Jenssen"]
