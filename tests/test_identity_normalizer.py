from app.identity_resolution import resolve_player_identity
from app.services.identity_normalizer import normalize_person_name, normalize_team_name


def test_normalize_person_name_folds_accents_and_punctuation() -> None:
    assert normalize_person_name('Nikola Jokić') == normalize_person_name('Nikola Jokic')
    assert normalize_person_name('Alperen Şengün') == normalize_person_name('Alperen Sengun')
    assert normalize_person_name('A.J. Brown') == normalize_person_name('AJ Brown')


def test_n_jokic_resolves_to_canonical_player() -> None:
    result = resolve_player_identity('N. Jokic', sport='NBA')
    assert result.resolved_player_name == 'Nikola Jokic'
    assert result.match_method in {'alias', 'normalized', 'canonical'}


def test_ambiguous_surname_only_is_low_confidence() -> None:
    result = resolve_player_identity('Williams', sport='NBA')
    assert result.confidence_level == 'LOW'
    assert result.ambiguity_reason == 'player identity ambiguous'


def test_team_abbreviation_normalization() -> None:
    assert normalize_team_name('L.A. Clippers') == normalize_team_name('LA Clippers')
    assert normalize_team_name('N.Y. Knicks') == normalize_team_name('NY Knicks')

def test_single_token_shorthand_resolves_unique_player() -> None:
    luka = resolve_player_identity('Luka', sport='NBA')
    tatum = resolve_player_identity('Tatum', sport='NBA')

    assert luka.resolved_player_name == 'Luka Doncic'
    assert luka.match_method in {'single_token_shorthand', 'single_token_first_name', 'single_token_first_name_heuristic'}
    assert tatum.resolved_player_name == 'Jayson Tatum'
    assert tatum.match_method in {'alias', 'single_token_shorthand'}


def test_shai_gilly_alexander_single_strong_candidate_resolves() -> None:
    result = resolve_player_identity('shai gilly alexander', sport='NBA')
    assert result.resolved_player_name == 'Shai Gilgeous-Alexander'
    assert result.resolved_player_id is not None
    assert result.match_method == 'single_strong_candidate'


def test_dehyphenated_gilgeous_alexander_resolves() -> None:
    result = resolve_player_identity('shai gilgeous alexander', sport='NBA')
    assert result.resolved_player_name == 'Shai Gilgeous-Alexander'
    assert result.resolved_player_id is not None


def test_multiple_close_candidates_still_review() -> None:
    result = resolve_player_identity('Williams', sport='NBA')
    assert result.resolved_player_id is None
    assert result.confidence_level == 'LOW'
    assert result.match_method == 'ambiguous'


def test_unresolved_identity_returns_top_three_candidate_players() -> None:
    result = resolve_player_identity('Xyzqv', sport='NBA')
    assert result.resolved_player_id is None
    assert result.ambiguity_reason == 'player not found in sport directory'
    assert len(result.candidate_players) >= 3
    assert len(result.candidate_player_details) >= 3
