from src.intelligence_core import BANNED_WORDS, apply_language_standards


def test_banned_words_cover_public_style_risks():
    assert "delve" in BANNED_WORDS
    assert "game changer" in BANNED_WORDS
    assert "excited to share" in BANNED_WORDS


def test_apply_language_standards_replacements():
    text = "We will leverage synergies and delve into a game changer."
    cleaned = apply_language_standards(text)

    assert "leverage" not in cleaned.lower()
    assert "delve" not in cleaned.lower()
    assert "game changer" not in cleaned.lower()
    assert "coordinate work" in cleaned.lower()
