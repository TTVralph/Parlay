from app.services.market_registry import normalize_market


def test_normalize_market_aliases_and_combos() -> None:
    cases = {
        'points': 'points',
        'PTS': 'points',
        'reb': 'rebounds',
        'AST': 'assists',
        'stl': 'steals',
        'blk': 'blocks',
        'TO': 'turnovers',
        '3pt made': 'three_pointers_made',
        '3PTM': 'three_pointers_made',
        'FGM': 'field_goals_made',
        'FTM': 'free_throws_made',
        'pr': 'points_rebounds',
        'pts+reb': 'points_rebounds',
        'pa': 'points_assists',
        'pts+ast': 'points_assists',
        'ra': 'rebounds_assists',
        'reb+ast': 'rebounds_assists',
        'PRA': 'points_rebounds_assists',
        'pts+reb+ast': 'points_rebounds_assists',
        'stocks': 'steals_blocks',
        'pts+3pm': 'points_threes',
        'reb+blk': 'rebounds_blocks',
    }

    for raw, expected in cases.items():
        assert normalize_market(raw) == expected


def test_normalize_market_milestones_and_alternate_lines() -> None:
    assert normalize_market('25+ pts') == 'points_milestone'
    assert normalize_market('20+ pts+reb+ast') == 'points_rebounds_assists_milestone'
    assert normalize_market('alt points line') == 'points_alternate_line'


def test_normalize_market_unsupported_returns_none() -> None:
    assert normalize_market('passing yards') is None


def test_normalize_market_play_by_play_aliases() -> None:
    assert normalize_market('first basket') == 'first_basket'
    assert normalize_market('to score first') == 'first_basket'
    assert normalize_market('first rebound') == 'first_rebound'
    assert normalize_market('first assist') == 'first_assist'
    assert normalize_market('first 3 pointer') == 'first_three'
    assert normalize_market('last bucket') == 'last_basket'
