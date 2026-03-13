from app.models import Leg
from app.rules.registry import get_stat_rule
from app.services.event_snapshot import EventSnapshot


def _snapshot(stats: dict[str, float]) -> EventSnapshot:
    return EventSnapshot(
        event_id='evt-1',
        sport='NBA',
        normalized_player_stats={
            'p1': {'player_id': 'p1', 'display_name': 'Test Player', 'stats': stats},
        },
        event_status='final',
    )


def test_nba_points_rule_computes_and_compares() -> None:
    rule = get_stat_rule('NBA', 'player_points')
    assert rule is not None
    actual = rule.compute_actual_value(_snapshot({'PTS': 27}), 'p1', 'Test Player')
    assert actual == 27
    assert rule.compare(actual, 24.5, 'over') == 'win'


def test_nba_combo_pra_rule_computes() -> None:
    rule = get_stat_rule('NBA', 'player_pra')
    assert rule is not None
    actual = rule.compute_actual_value(_snapshot({'PTS': 21, 'REB': 9, 'AST': 8}), 'p1', 'Test Player')
    assert actual == 38


def test_starter_multi_sport_rules_compute() -> None:
    wnba = get_stat_rule('WNBA', 'player_points')
    mlb = get_stat_rule('MLB', 'player_total_bases')
    nfl = get_stat_rule('NFL', 'player_passing_yards')
    assert wnba and mlb and nfl

    snap_wnba = _snapshot({'PTS': 18})
    snap_mlb = _snapshot({'1B': 1, '2B': 1, '3B': 0, 'HR': 1})
    snap_nfl = _snapshot({'passing_yards': 286})

    assert wnba.compute_actual_value(snap_wnba, 'p1', 'Test Player') == 18
    assert mlb.compute_actual_value(snap_mlb, 'p1', 'Test Player') == 7
    assert nfl.compute_actual_value(snap_nfl, 'p1', 'Test Player') == 286


def test_unsupported_or_missing_stat_fails_gracefully() -> None:
    rule = get_stat_rule('SOCCER', 'player_shots_on_target')
    assert rule is not None
    assert rule.compute_actual_value(_snapshot({'SHOTS': 4}), 'p1', 'Test Player') is None
    assert get_stat_rule('NBA', 'player_unknown_market') is None


def test_rule_dispatch_by_sport() -> None:
    assert get_stat_rule('NBA', 'player_points') is not None
    assert get_stat_rule('MLB', 'player_points') is None


def test_live_progress_uses_rule_metadata() -> None:
    from app.grader import _build_live_progress_payload

    leg = Leg(raw_text='x', sport='NBA', market_type='player_pra', player='Test Player', direction='over', line=40.5)
    payload = _build_live_progress_payload(leg, actual_value=35, line=40.5, component_values={'PTS': 20, 'REB': 10, 'AST': 5})
    assert payload is not None
    assert payload['remaining_to_hit'] == 5.5
