from app.models import GradedLeg, Leg
from app.services.espn_plays_provider import ESPNPlayFeedResult, ESPNPlaysProvider
from app.services.event_snapshot import EventSnapshot
from app.services.kill_moment_explainer import explain_kill_moment
from app.services.play_by_play_provider import PlayByPlayEvent


class StubESPNPlaysProvider(ESPNPlaysProvider):
    def __init__(self, result: ESPNPlayFeedResult | None):
        super().__init__()
        self._result = result

    def get_best_play_feed(self, event_id: str, *, sport: str = 'basketball', league: str = 'nba', limit: int = 500):
        return self._result


def _graded_leg(*, market_type: str, settlement: str = 'loss', direction: str | None = 'over', line: float | None = 4.5, actual: float | None = 4.0, player: str | None = 'Kevin Durant', team: str | None = None, event_id: str = 'evt-1', component_values=None) -> GradedLeg:
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


def test_player_stat_kill_moment_uses_last_relevant_pbp_play() -> None:
    graded = _graded_leg(market_type='player_points', line=28.5, actual=11.0)
    snapshot = EventSnapshot(
        event_id='evt-1',
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='play', description='Kevin Durant makes 2-pt jump shot', period=3, clock='06:21', team='Suns', primary_player='Kevin Durant', is_made_shot=True, is_scoring_play=True),
            PlayByPlayEvent(event_order=2, event_type='play', description='Other player makes 3-pt jump shot', period=4, clock='01:10', team='Nuggets', primary_player='Other', is_three_pointer_made=True, is_made_shot=True, is_scoring_play=True),
        ],
    )

    explanation = explain_kill_moment(graded, snapshot, graded.settlement)
    assert explanation is not None
    assert explanation.kill_moment_supported is True
    assert explanation.explanation_source == 'snapshot_plus_pbp'
    assert explanation.last_relevant_play_text == 'Kevin Durant makes 2-pt jump shot'
    assert explanation.last_relevant_period == 'Q3'
    assert explanation.last_relevant_clock == '06:21'


def test_combo_market_kill_moment_reports_components_and_last_component_play() -> None:
    graded = _graded_leg(
        market_type='player_pra',
        line=33.5,
        actual=31.0,
        component_values={'PTS': 22.0, 'REB': 6.0, 'AST': 3.0},
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='play', description='Teammate makes 2-pt shot, assist by Kevin Durant', period=4, clock='08:12', team='Suns', primary_player='Teammate', assist_player='Kevin Durant', is_assist=True, is_scoring_play=True),
        ],
    )

    explanation = explain_kill_moment(graded, snapshot, graded.settlement)
    assert explanation is not None
    assert explanation.explanation_source == 'snapshot_plus_pbp'
    assert '31 PRA (22 PTS, 6 REB, 3 AST)' in explanation.kill_moment_summary
    assert 'last AST play that changed the total came with 08:12 left in Q4' in explanation.kill_moment_summary


def test_team_market_spread_and_total_kill_moment() -> None:
    spread = _graded_leg(market_type='spread', player=None, team='Lakers', direction='over', line=-3.5, actual=-2.0)
    total = _graded_leg(market_type='game_total', player=None, team=None, direction='under', line=224.5, actual=230.0)
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Lakers'},
        away_team={'name': 'Celtics'},
        normalized_event_result={'home_score': 100, 'away_score': 104, 'margin': -4, 'combined_total': 204},
        normalized_play_by_play=[
            PlayByPlayEvent(event_order=1, event_type='play', description='Celtics make 3-pt shot to push late margin', period=4, clock='00:50', team='Celtics', primary_player='Other', is_scoring_play=True, is_made_shot=True, is_three_pointer_made=True),
        ],
    )

    spread_explanation = explain_kill_moment(spread, snapshot, spread.settlement)
    total_explanation = explain_kill_moment(total, snapshot, total.settlement)

    assert spread_explanation is not None
    assert spread_explanation.last_relevant_play_text is not None
    assert 'failed to cover' in spread_explanation.kill_moment_summary

    assert total_explanation is not None
    assert total_explanation.last_relevant_play_text is not None
    assert 'final scoring swing' in total_explanation.kill_moment_summary


def test_fetches_experimental_feed_when_snapshot_lacks_play_by_play() -> None:
    graded = _graded_leg(market_type='player_rebounds', actual=5.0)
    snapshot = EventSnapshot(event_id='evt-3', normalized_play_by_play=None)
    provider = StubESPNPlaysProvider(
        ESPNPlayFeedResult(
            source='espn_core_plays',
            plays=[
                PlayByPlayEvent(
                    event_order=1,
                    event_type='play',
                    description='Kevin Durant defensive rebound',
                    period=4,
                    clock='05:42',
                    team='Suns',
                    primary_player='Kevin Durant',
                    is_rebound=True,
                )
            ],
        )
    )

    explanation = explain_kill_moment(graded, snapshot, graded.settlement, plays_provider=provider)
    assert explanation is not None
    assert explanation.explanation_source == 'espn_core_plays'
    assert "final rebound came with 05:42 left in Q4" in explanation.kill_moment_summary


def test_snapshot_only_fallback_and_no_win_labeling() -> None:
    losing = _graded_leg(market_type='player_assists', line=7.5, actual=0.0)
    no_pbp_snapshot = EventSnapshot(
        event_id='evt-1',
        normalized_player_stats={
            'durant': {'display_name': 'Kevin Durant', 'stats': {'AST': 0}},
        },
    )

    fallback = explain_kill_moment(losing, no_pbp_snapshot, losing.settlement, plays_provider=StubESPNPlaysProvider(None))
    assert fallback is not None
    assert fallback.explanation_source == 'snapshot_only'
    assert fallback.last_relevant_play_text is None
    assert 'never materialized' in fallback.kill_moment_summary

    winning = _graded_leg(market_type='player_assists', settlement='win', line=7.5, actual=8.0)
    assert explain_kill_moment(winning, no_pbp_snapshot, winning.settlement) is None


def test_review_and_live_states_are_excluded() -> None:
    review = _graded_leg(market_type='moneyline', settlement='review', player=None, team='Lakers')
    live = _graded_leg(market_type='moneyline', settlement='live', player=None, team='Lakers')
    assert explain_kill_moment(review, EventSnapshot(event_id='evt-5'), review.settlement) is None
    assert explain_kill_moment(live, EventSnapshot(event_id='evt-5'), live.settlement) is None
