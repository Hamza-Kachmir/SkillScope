from app.normalizer import display_label, search_key


def test_display_label_capitalizes_only_the_first_letter() -> None:
    assert display_label("lecteur de plans") == "Lecteur de plans"
    assert display_label("Power BI") == "Power BI"
    assert display_label("  machine   learning ") == "Machine learning"


def test_search_key_normalizes_accents_and_punctuation() -> None:
    assert search_key("  Modélisation des données  ") == "modelisation des donnees"
