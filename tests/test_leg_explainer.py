from app.models import GradeResponse, GradedLeg, Leg
from app.services.event_snapshot import EventSnapshot
from app.services.leg_explainer import explain_sold_legs
from app.services.play_by_play_provider import PlayByPlayEvent


def _graded_leg(*, market_type: str, settlement: str = 'loss', direction: str | None = 'over', line: float | None = 4.5, actual: float | None = 4.0, player: str | None = 'Donovan Mitchell', team: str | None = None, event_id: str = 'evt-1', component_values=None) -> GradedLeg:
    leg = Leg(
        raw_text='x',
        sport='NBA',
        market_type=market_type,
        player=player,
        team=team,
        direction=direction,
        line=line,
        confidence=0.9,
        event_id=event_id,
        event_label='Away @ Home',
        resolved_player_name=player,
    )
    return GradedLeg(leg=leg, settlement=settlement, reason='r', actual_value=actual, component_values=component_values)


def test_losing_player_stat_explanation_with_pbp_context() -> None:
    graded = _graded_leg(market_type='player_assists', line=4.5, actual=4.0)
    snapshot = EventSnapshot(
        event_id='evt-1',
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='play', description='Donovan Mitchell makes pass, assist by Donovan Mitchell', period=4, clock='08:12', team='Cavs', primary_player='Other', assist_player='Donovan Mitchell', is_assist=True),
        ],
    )
    response = GradeResponse(overall='lost', legs=[graded])

    sold = explain_sold_legs(response, {'evt-1': snapshot})
    assert len(sold) == 1
    assert sold[0].is_sold_leg is True
    assert sold[0].market_type == 'player_assists'
    assert sold[0].miss_by == 0.5
    assert sold[0].explanation_source == 'snapshot_plus_pbp'
    assert sold[0].last_relevant_context is not None


def test_losing_combo_stat_explanation_includes_components() -> None:
    graded = _graded_leg(
        market_type='player_pra',
        line=33.5,
        actual=31.0,
        component_values={'PTS': 22.0, 'REB': 6.0, 'AST': 3.0},
    )
    response = GradeResponse(overall='lost', legs=[graded])

    sold = explain_sold_legs(response)
    assert len(sold) == 1
    assert '22 PTS' in sold[0].detailed_reason
    assert '6 REB' in sold[0].detailed_reason
    assert '3 AST' in sold[0].detailed_reason


def test_losing_team_market_explanations() -> None:
    moneyline_leg = _graded_leg(market_type='moneyline', player=None, team='Lakers', direction=None, line=None, actual=0.0)
    spread_leg = _graded_leg(market_type='spread', player=None, team='Lakers', direction='over', line=-3.5, actual=-2.0, event_id='evt-2')
    total_leg = _graded_leg(market_type='game_total', player=None, team=None, direction='under', line=224.5, actual=230.0, event_id='evt-3')
    response = GradeResponse(overall='lost', legs=[moneyline_leg, spread_leg, total_leg])

    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Lakers'},
        away_team={'name': 'Celtics'},
        normalized_event_result={'home_score': 100, 'away_score': 104},
    )
    sold = explain_sold_legs(response, {'evt-1': snapshot})
    assert len(sold) == 3
    assert any(item.market_type == 'moneyline' for item in sold)
    assert any(item.market_type == 'spread' for item in sold)
    assert any(item.market_type == 'game_total' for item in sold)


def test_no_play_by_play_fallback_explanation() -> None:
    graded = _graded_leg(market_type='player_points', line=30.5, actual=29.0)
    response = GradeResponse(overall='lost', legs=[graded])

    sold = explain_sold_legs(response, {'evt-1': EventSnapshot(event_id='evt-1')})
    assert len(sold) == 1
    assert sold[0].explanation_source == 'snapshot_only'
    assert sold[0].last_relevant_context is None


def test_winning_legs_not_marked_sold() -> None:
    graded = _graded_leg(market_type='player_points', settlement='win', line=24.5, actual=28.0)
    response = GradeResponse(overall='cashed', legs=[graded])
    assert explain_sold_legs(response) == []


def test_multiple_losing_legs_each_get_explanation() -> None:
    leg1 = _graded_leg(market_type='player_rebounds', line=10.5, actual=9.0, event_id='evt-1')
    leg2 = _graded_leg(market_type='player_assists', line=8.5, actual=7.0, event_id='evt-2')
    response = GradeResponse(overall='lost', legs=[leg1, leg2])

    sold = explain_sold_legs(response)
    assert len(sold) == 2
    assert {item.market_type for item in sold} == {'player_rebounds', 'player_assists'}


def test_live_leg_not_selected_for_sold_or_kill_moment() -> None:
    live_leg = _graded_leg(market_type='player_assists', settlement='live', line=6.5, actual=4.0)
    response = GradeResponse(overall='pending', legs=[live_leg])
    assert explain_sold_legs(response) == []


def test_finalized_losing_leg_still_gets_sold_explanation() -> None:
    loss_leg = _graded_leg(market_type='player_points', settlement='loss', line=30.5, actual=29.0)
    response = GradeResponse(overall='lost', legs=[loss_leg])

    sold = explain_sold_legs(response, {'evt-1': EventSnapshot(event_id='evt-1')})
    assert len(sold) == 1
    assert sold[0].kill_moment_supported is True
