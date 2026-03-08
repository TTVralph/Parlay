from app.ocr.providers import _normalize_sportsbook_ocr_text


def test_normalize_sportsbook_ocr_text_preserves_leg_line_breaks_and_drops_junk() -> None:
    text = """Bet Slip
Cash Out
Nikola Jokic over 24.5 points
Jamal Murray 2+ threes
+240
Place Bet"""
    cleaned, unusable = _normalize_sportsbook_ocr_text(text)
    assert unusable is False
    assert cleaned == 'Nikola Jokic over 24.5 points\nJamal Murray 2+ threes'


def test_normalize_sportsbook_ocr_text_flags_unusable_output() -> None:
    text = """Bet Slip
Cash Out
Popular
Live
Promos"""
    cleaned, unusable = _normalize_sportsbook_ocr_text(text)
    assert cleaned == ''
    assert unusable is True
