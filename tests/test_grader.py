from datetime import datetime

from app.grader import grade_text
from app.services.slip_fingerprint import reset_slip_hash_index


def test_grade_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    result = grade_text(text, posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    assert result.overall == 'lost'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'
    assert result.legs[2].settlement == 'loss'


def test_grade_unverified_slip_is_needs_review() -> None:
    result = grade_text('Leg A\nLeg B')
    assert result.overall == 'needs_review'
    assert all(item.settlement == 'unmatched' for item in result.legs)


def test_grade_live_or_unresolved_stats_is_pending() -> None:
    result = grade_text('Nikola Jokic over 250.5 passing yards')
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'


def test_grade_only_verified_wins_is_cashed() -> None:
    result = grade_text('Jokic 25+ pts\nDenver ML', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    assert result.overall == 'cashed'
    assert all(item.settlement == 'win' for item in result.legs)


def test_jokic_threes_made_alias_settles_as_loss_on_2026_03_06() -> None:
    result = grade_text('Nikola Jokic Over 1.5 Threes Made', posted_at=datetime.fromisoformat('2026-03-06T00:00:00'))
    assert result.legs[0].leg.event_label == 'New York Knicks @ Denver Nuggets'
    assert result.legs[0].settlement == 'loss'


def test_cooper_flagg_pra_combo_settles_as_win_on_2026_03_06() -> None:
    result = grade_text('Cooper Flagg Over 25.5 PRA', posted_at=datetime.fromisoformat('2026-03-06T00:00:00'))
    assert result.legs[0].leg.event_label == 'Dallas Mavericks @ Boston Celtics'
    assert result.legs[0].actual_value == 30
    assert result.legs[0].settlement == 'win'


def test_standard_points_prop_includes_explanation_fields() -> None:
    result = grade_text('Jokic over 24.5 points', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    leg = result.legs[0]
    assert leg.normalized_market == 'Points'
    assert leg.line == 24.5
    assert leg.actual_value is not None
    assert leg.matched_event is not None


def test_threes_made_prop_explanation_uses_actual_value() -> None:
    result = grade_text('Nikola Jokic Over 1.5 Threes Made', posted_at=datetime.fromisoformat('2026-03-06T00:00:00'))
    leg = result.legs[0]
    assert leg.normalized_market == 'Threes Made'
    assert leg.actual_value == 1
    assert leg.settlement == 'loss'


def test_pra_prop_explanation_includes_component_values() -> None:
    result = grade_text('Cooper Flagg Over 25.5 PRA', posted_at=datetime.fromisoformat('2026-03-06T00:00:00'))
    leg = result.legs[0]
    assert leg.component_values == {'Points': 16.0, 'Rebounds': 8.0, 'Assists': 6.0}
    assert leg.actual_value == 30
    assert leg.settlement == 'win'


def test_review_explanation_when_multiple_candidate_games_exist() -> None:
    result = grade_text('Jokic over 24.5 points', posted_at=datetime.fromisoformat('2026-03-01T00:00:00'), include_historical=True)
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert leg.explanation_reason in {'multiple games found for resolved team on date','Multiple plausible games were found for this player/date.'}
    assert len(leg.candidate_games) > 1



class _VoidProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo
        return EventInfo(event_id='evt-1', sport='NBA', home_team='Denver Nuggets', away_team='Boston Celtics', start_time=datetime.utcnow())

    def get_player_result(self, player: str, market_type: str, event_id=None):
        return None

    def get_event_status(self, event_id: str):
        return 'final'

    def did_player_appear(self, player: str, event_id=None):
        return False


def test_void_explanation_when_player_did_not_play() -> None:
    result = grade_text('Nikola Jokic over 8.5 points', provider=_VoidProvider())
    leg = result.legs[0]
    assert leg.settlement == 'void'
    assert leg.player_found_in_boxscore is False
    assert leg.explanation_reason == 'player did not appear in box score / game log'


def test_missing_bet_date_produces_helpful_review_reason() -> None:
    result = grade_text('Jamal Murray over 2.5 threes')
    assert result.overall == 'needs_review'
    assert result.legs[0].review_reason in {'Multiple possible games. Add bet date to narrow results.','Multiple plausible games were found for this player/date.'}


def test_missing_bet_date_can_still_autosettle_when_single_candidate_exists() -> None:
    result = grade_text('Jayson Tatum over 25.5 points', posted_at=datetime.fromisoformat('2026-03-08T00:00:00'))
    assert result.legs[0].leg.event_id == 'nba-2026-03-08-bos-gsw'


def test_bet_date_autoselects_single_team_game() -> None:
    result = grade_text('Jamal Murray over 2.5 threes', posted_at=datetime.fromisoformat('2026-03-09T00:00:00'))
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'


class _MatchedBoxScoreProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo
        return EventInfo(event_id='evt-2', sport='NBA', home_team='Golden State Warriors', away_team='Boston Celtics', start_time=datetime.utcnow())

    def get_player_result_details(self, player: str, market_type: str, event_id=None):
        return {'actual_value': 6.0, 'matched_boxscore_player_name': 'Draymond Green'}

    def get_player_result(self, player: str, market_type: str, event_id=None):
        return 6.0

    def get_event_status(self, event_id: str):
        return 'final'


def test_grading_includes_matched_boxscore_player_name() -> None:
    result = grade_text('Draymond Green over 4.5 assists', provider=_MatchedBoxScoreProvider())
    leg = result.legs[0]
    assert leg.settlement == 'win'
    assert leg.matched_boxscore_player_name == 'Draymond Green'
    assert leg.player_found_in_boxscore is True


class _LivePropProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo

        if 'giddey' in player.lower():
            return EventInfo(event_id='evt-live', sport='NBA', home_team='Los Angeles Lakers', away_team='Chicago Bulls', start_time=datetime.utcnow())
        return EventInfo(event_id='evt-final', sport='NBA', home_team='Denver Nuggets', away_team='Boston Celtics', start_time=datetime.utcnow())

    def get_player_result(self, player: str, market_type: str, event_id=None):
        if event_id == 'evt-live':
            return 0.0
        return 10.0

    def get_event_status(self, event_id: str):
        return 'live' if event_id == 'evt-live' else 'final'


def test_live_prop_leg_is_not_graded_before_final() -> None:
    result = grade_text('Josh Giddey over 8.5 assists', provider=_LivePropProvider())
    leg = result.legs[0]
    assert result.overall == 'pending'
    assert leg.settlement == 'live'
    assert leg.actual_value == 0.0


def test_live_under_leg_marks_kill_moment_when_threshold_exceeded() -> None:
    class _LiveKillProvider(_LivePropProvider):
        def get_player_result(self, player: str, market_type: str, event_id=None):
            return 10.0 if event_id == 'evt-live' else super().get_player_result(player, market_type, event_id=event_id)

    result = grade_text('Josh Giddey under 8.5 assists', provider=_LiveKillProvider())
    leg = result.legs[0]
    assert leg.settlement == 'loss'
    assert leg.actual_value == 10.0
    assert leg.kill_moment is True
    assert leg.kill_reason == 'threshold_exceeded'


def test_parlay_can_be_lost_with_final_loss_and_live_legs() -> None:
    result = grade_text('Josh Giddey over 8.5 assists\nNikola Jokic over 12.5 points', provider=_LivePropProvider())
    assert result.overall == 'lost'
    assert result.legs[0].settlement == 'live'
    assert result.legs[1].settlement == 'loss'


def test_slip_hash_same_slip_different_order_matches() -> None:
    reset_slip_hash_index()
    first = grade_text('Jokic over 24.5 points\nMurray over 1.5 threes', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    second = grade_text('Murray over 1.5 threes\nJokic over 24.5 points', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))

    assert first.slip_hash == second.slip_hash
    assert second.grading_diagnostics['fingerprint']['duplicate_slip_count'] >= 1
    assert second.grading_diagnostics['fingerprint']['unique_slip_count'] >= 1


def test_slip_hash_normalizes_player_aliases() -> None:
    reset_slip_hash_index()
    alias_slip = grade_text('SGA over 6 assists', posted_at=datetime.fromisoformat('2026-03-09T00:00:00'))
    canonical_slip = grade_text('Shai Gilgeous-Alexander over 6 assists', posted_at=datetime.fromisoformat('2026-03-09T00:00:00'))

    assert alias_slip.slip_hash == canonical_slip.slip_hash


def test_slip_hash_differs_for_different_slips() -> None:
    reset_slip_hash_index()
    first = grade_text('Jokic over 24.5 points', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    second = grade_text('Jokic under 24.5 points', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))

    assert first.slip_hash != second.slip_hash
