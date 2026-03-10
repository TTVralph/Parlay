from app.services.player_name_suggester import suggest_player_name


def test_obvious_shai_misspelling_gets_high_confidence_suggestion() -> None:
    suggestion = suggest_player_name('Shai Gilly-Alexander', sport='NBA')
    assert suggestion is not None
    assert suggestion.suggested_name == 'Shai Gilgeous-Alexander'
    assert suggestion.confidence_level == 'HIGH'
    assert suggestion.auto_applied is True


def test_hard_last_names_get_suggestions() -> None:
    giannis = suggest_player_name('Giannis Antetokunpmo', sport='NBA')
    victor = suggest_player_name('Victor Wembanyana', sport='NBA')
    tyrese = suggest_player_name('Tyrese Haliberton', sport='NBA')

    assert giannis is not None and giannis.suggested_name == 'Giannis Antetokounmpo'
    assert victor is not None and victor.suggested_name == 'Victor Wembanyama'
    assert tyrese is not None and tyrese.suggested_name == 'Tyrese Haliburton'


def test_low_confidence_junk_text_does_not_suggest() -> None:
    assert suggest_player_name('xxxyyzz random token', sport='NBA') is None
    assert suggest_player_name('Boosted Parlay Winner', sport='NBA') is None
