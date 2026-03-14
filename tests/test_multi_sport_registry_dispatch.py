from __future__ import annotations

from app.markets import get_market_registry
from app.models import Leg
from app.services.market_registry import normalize_market, player_market_to_canonical
from app.services.sport_resolver_hooks import apply_sport_resolver_hook


def test_nba_market_registry_unchanged_basics() -> None:
    registry = get_market_registry('NBA')
    assert 'points' in registry
    assert registry['first_basket']['required_data_source'] == 'play_by_play'
    assert normalize_market('25+ pts', sport='NBA') == 'points_milestone'


def test_sport_registry_loads_for_supported_sports() -> None:
    assert get_market_registry('NBA')
    assert isinstance(get_market_registry('MLB'), dict)
    assert isinstance(get_market_registry('NFL'), dict)
    assert get_market_registry('WNBA')


def test_generic_market_dispatch_by_sport() -> None:
    assert player_market_to_canonical('player_points', sport='NBA') == 'points'
    assert player_market_to_canonical('player_points', sport='WNBA') == 'points'
    assert player_market_to_canonical('player_points', sport='MLB') is None


def test_wnba_registry_resolves_combo_and_threes_markets() -> None:
    assert normalize_market('3PTM', sport='WNBA') == 'three_pointers_made'
    assert normalize_market('PRA', sport='WNBA') == 'points_rebounds_assists'
    assert player_market_to_canonical('player_threes', sport='WNBA') == 'three_pointers_made'
    assert player_market_to_canonical('player_pra', sport='WNBA') == 'points_rebounds_assists'


def test_unsupported_sport_features_fail_gracefully() -> None:
    assert normalize_market('passing yards', sport='NBA') is None
    assert normalize_market('points', sport='CRICKET') is None


def test_resolver_hooks_dispatch_without_breaking_candidates() -> None:
    leg = Leg(raw_text='Nikola Jokic over 24.5 points', market_type='player_points', line=24.5, selection='over', sport='NBA')
    assert apply_sport_resolver_hook(leg, [], None) == []
