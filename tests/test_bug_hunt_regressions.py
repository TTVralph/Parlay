from __future__ import annotations

from datetime import date, datetime, timezone

from app.grader import _compute_leg_progress, _compute_slip_progress
from app.models import GradedLeg, Leg
from app.parser import parse_text
from app.player_identity import resolve_player_resolution
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events
from app.rules.helpers import compute_combo_stat, get_player_stat
from app.rules.registry import get_stat_rule
from app.services.event_snapshot import EventSnapshot
from app.services.kill_moment_explainer import get_last_relevant_stat_play
from app.services.play_by_play_provider import PlayByPlayEvent


class _AmbiguousPlayerProvider:
    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [
            EventInfo(
                event_id='evt-a',
                sport='NBA',
                away_team='Denver Nuggets',
                home_team='Oklahoma City Thunder',
                start_time=datetime(2026, 3, 7, 1, 0, tzinfo=timezone.utc),
            ),
            EventInfo(
                event_id='evt-b',
                sport='NBA',
                away_team='Denver Nuggets',
                home_team='Minnesota Timberwolves',
                start_time=datetime(2026, 3, 7, 3, 0, tzinfo=timezone.utc),
            ),
        ]

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None

    def did_player_appear(self, player: str, event_id: str | None = None):
        return None


def test_parser_handles_shorthand_hyphen_and_suffix_names() -> None:
    legs = parse_text('Jokic O28.5 PTS\nShai Gilgeous-Alexander O6.5 AST\nJaren Jackson Jr. U5.5 REB')

    assert len(legs) == 3

    assert legs[0].direction == 'over'
    assert legs[0].line == 28.5
    assert legs[0].market_type == 'player_points'
    assert legs[0].player == 'Nikola Jokic'

    assert legs[1].direction == 'over'
    assert legs[1].market_type == 'player_assists'
    assert legs[1].player == 'Shai Gilgeous-Alexander'

    assert legs[2].direction == 'under'
    assert legs[2].market_type == 'player_rebounds'
    assert legs[2].player == 'Jaren Jackson Jr.'


def test_player_resolver_handles_hyphen_and_suffix() -> None:
    sga = resolve_player_resolution('Shai Gilgeous-Alexander', sport='NBA')
    jaren = resolve_player_resolution('Jaren Jackson Jr.', sport='NBA')

    assert sga is not None and sga.resolved_player_name == 'Shai Gilgeous-Alexander'
    assert jaren is not None and jaren.resolved_player_name == 'Jaren Jackson Jr.'


def test_event_resolver_keeps_ambiguous_player_events_in_review() -> None:
    leg = Leg(
        raw_text='Nikola Jokic over 28.5 points',
        sport='NBA',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=28.5,
        confidence=0.9,
    )

    resolved = resolve_leg_events([leg], _AmbiguousPlayerProvider(), posted_at=date(2026, 3, 7), include_historical=True)

    assert resolved[0].event_id is None
    assert 'ambiguous_event_match' in resolved[0].event_resolution_warnings


def test_stat_normalization_supports_camel_case_total_bases() -> None:
    snapshot = EventSnapshot(
        event_id='mlb-1',
        normalized_player_stats={
            'p1': {
                'player_id': 'p1',
                'display_name': 'Mookie Betts',
                'stats': {'totalBases': 3},
            }
        },
    )

    assert get_player_stat(snapshot, 'p1', 'TB', player_name='Mookie Betts') == 3.0


def test_combo_stat_calculation_sums_components() -> None:
    snapshot = EventSnapshot(
        event_id='nba-1',
        normalized_player_stats={
            'jokic': {
                'player_id': 'jokic',
                'display_name': 'Nikola Jokic',
                'stats': {'PTS': 25, 'REB': 12, 'AST': 9},
            }
        },
    )

    assert compute_combo_stat(snapshot, 'jokic', ('PTS', 'REB', 'AST'), player_name='Nikola Jokic') == 46.0


def test_kill_moment_uses_last_assist_event() -> None:
    snapshot = EventSnapshot(
        event_id='nba-2',
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='assist', description='other assist', period=4, clock='2:00', team='Denver Nuggets', primary_player='Someone Else', is_assist=True, assist_player='Someone Else'),
            PlayByPlayEvent(event_order=2, event_type='assist', description='jokic assist', period=4, clock='0:45', team='Denver Nuggets', primary_player='Jamal Murray', is_assist=True, assist_player='Nikola Jokic'),
        ],
    )
    leg = Leg(raw_text='Nikola Jokic under 9.5 assists', sport='NBA', market_type='player_assists', player='Nikola Jokic', direction='under', line=9.5, confidence=0.9)

    event, stat_key = get_last_relevant_stat_play(leg=leg, snapshot=snapshot, stat_keys=('AST',))

    assert stat_key == 'AST'
    assert event is not None and event.description == 'jokic assist'


def test_under_progress_math_and_slip_aggregation() -> None:
    # Under legs should trend upward as the actual stays below the line.
    under_progress = _compute_leg_progress(actual_value=20.0, line=25.0, direction='under')
    over_progress = _compute_leg_progress(actual_value=20.0, line=25.0, direction='over')

    assert under_progress == 1.25
    assert over_progress == 0.8

    legs = [
        GradedLeg(leg=Leg(raw_text='under', sport='NBA', market_type='player_points', player='A', direction='under', line=25.0, confidence=0.9), settlement='live', reason='x', progress=under_progress),
        GradedLeg(leg=Leg(raw_text='over', sport='NBA', market_type='player_points', player='B', direction='over', line=25.0, confidence=0.9), settlement='live', reason='x', progress=over_progress),
    ]
    assert _compute_slip_progress(legs) == 1.02


def test_total_bases_derives_from_component_hits_when_tb_missing() -> None:
    snapshot = EventSnapshot(
        event_id='mlb-2',
        normalized_player_stats={
            'p1': {
                'player_id': 'p1',
                'display_name': 'Mookie Betts',
                'stats': {'singles': 1, 'doubles': 1, 'triples': 0, 'home_runs': 1},
            }
        },
    )
    rule = get_stat_rule('MLB', 'player_total_bases')
    assert rule is not None
    assert rule.compute_actual_value(snapshot, 'p1', 'Mookie Betts') == 7.0
