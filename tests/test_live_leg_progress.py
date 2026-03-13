from app.grader import _build_live_progress_payload, _build_live_progress_timeline
from app.models import Leg
from app.services.event_snapshot import EventSnapshot
from app.services.play_by_play_provider import PlayByPlayEvent


def _leg(market_type: str, direction: str = 'over', line: float = 30.5) -> Leg:
    return Leg(
        raw_text='x',
        sport='NBA',
        market_type=market_type,
        player='LeBron James',
        direction=direction,
        line=line,
        confidence=0.8,
        event_id='evt-1',
        event_label='A @ B',
        resolved_player_name='LeBron James',
    )


def test_live_progress_payload_generation_for_points() -> None:
    payload = _build_live_progress_payload(
        _leg('player_points', line=28.5),
        actual_value=22.0,
        line=28.5,
        component_values=None,
    )
    assert payload is not None
    assert payload['current_stat_value'] == 22.0
    assert payload['target_value'] == 28.5
    assert payload['remaining_to_hit'] == 6.5


def test_combo_market_progress_breakdown() -> None:
    payload = _build_live_progress_payload(
        _leg('player_pra', line=40.5),
        actual_value=34.0,
        line=40.5,
        component_values={'Points': 20.0, 'Rebounds': 9.0, 'Assists': 5.0},
    )
    assert payload is not None
    assert payload['remaining_to_hit'] == 6.5
    assert payload['component_breakdown'] == {'PTS': 20.0, 'REB': 9.0, 'AST': 5.0}


def test_live_progress_timeline_derives_by_period() -> None:
    snapshot = EventSnapshot(
        event_id='evt-1',
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='shot', description='LeBron makes 2-pt', period=1, clock='08:00', team='A', primary_player='LeBron James', is_made_shot=True),
            PlayByPlayEvent(event_order=2, event_type='ast', description='teammate makes shot assist by LeBron', period=2, clock='06:00', team='A', primary_player='Other', assist_player='LeBron James', is_assist=True),
            PlayByPlayEvent(event_order=3, event_type='reb', description='LeBron defensive rebound', period=2, clock='05:00', team='A', primary_player='LeBron James', is_rebound=True),
        ],
    )
    timeline = _build_live_progress_timeline(_leg('player_pra'), snapshot, player_name='LeBron James')
    assert len(timeline) == 2
    assert timeline[0]['period_label'] == 'Q1'
    assert timeline[1]['period_label'] == 'Q2'
    assert timeline[1]['cumulative'] == {'PTS': 2.0, 'REB': 1.0, 'AST': 1.0}
