from app.services.market_registry import normalize_market


def test_normalize_market_aliases() -> None:
    cases = {
        'points': 'points',
        'pts': 'points',
        'reb': 'rebounds',
        'ast': 'assists',
        '3pt made': 'threes',
        'stl': 'steals',
        'blk': 'blocks',
        'tov': 'turnovers',
        'pra': 'pra',
        'p+r+a': 'pra',
        'pts+reb+ast': 'pra',
        'points rebounds assists': 'pra',
        'pr': 'pr',
        'p+r': 'pr',
        'pts+reb': 'pr',
        'pa': 'pa',
        'p+a': 'pa',
        'pts+ast': 'pa',
        'ra': 'ra',
        'r+a': 'ra',
        'reb+ast': 'ra',
    }

    for raw, expected in cases.items():
        assert normalize_market(raw) == expected


def test_normalize_market_unsupported_returns_none() -> None:
    assert normalize_market('passing yards') is None
