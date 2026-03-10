from datetime import datetime, timezone

from app.grader import grade_text
from app.models import Leg
from app.providers.base import EventInfo


class DnpProvider:
    def __init__(self) -> None:
        self.event = EventInfo(event_id='evt-1', sport='NBA', home_team='Denver Nuggets', away_team='LA Clippers', start_time=datetime(2026, 3, 8, tzinfo=timezone.utc))

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return self.event

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return self.event

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self.event]

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self.event]

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_event_status(self, event_id: str):
        return 'final'

    def did_player_appear(self, player: str, event_id: str | None = None):
        return False


class MissingStatProvider(DnpProvider):
    def did_player_appear(self, player: str, event_id: str | None = None):
        return True


class ImpossibleEventProvider(DnpProvider):
    def get_event_info(self, event_id: str):
        return {'home_team': 'Boston Celtics', 'away_team': 'New York Knicks'}


def test_normal_win_explanation_contains_stat_and_reason_code() -> None:
    result = grade_text('Jokic over 24.5 points', posted_at=datetime.fromisoformat('2026-03-07T18:15:00'))
    leg = result.legs[0]
    assert leg.settlement == 'win'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.actual_stat_value == 27.0
    assert leg.settlement_explanation.settlement_reason_code == 'actual_stat_above_line'
    assert leg.settlement_explanation.matched_player == 'Nikola Jokic'
    assert leg.settlement_explanation.selection == 'over 24.5'
    assert leg.settlement_explanation.settlement_reason_text == '27.0 is above 24.5'


def test_normal_loss_explanation_contains_reason_message() -> None:
    result = grade_text('Jokic over 40.5 points', posted_at=datetime.fromisoformat('2026-03-07T18:15:00'))
    leg = result.legs[0]
    assert leg.settlement == 'loss'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.settlement_reason_code == 'actual_stat_below_line'
    assert leg.settlement_explanation.settlement_reason_text == '27.0 is below 40.5'


def test_dnp_void_explanation() -> None:
    result = grade_text('Jokic over 24.5 points', provider=DnpProvider(), posted_at=datetime.fromisoformat('2026-03-07T18:15:00'))
    leg = result.legs[0]
    assert leg.settlement == 'void'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.settlement_reason_code == 'player_did_not_play'
    assert leg.settlement_explanation.settlement_reason_text == 'Player did not appear in box score'


def test_impossible_event_review_explanation() -> None:
    result = grade_text('Jokic over 24.5 points', provider=ImpossibleEventProvider(), posted_at=datetime.fromisoformat('2026-03-07T18:15:00'))
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.settlement_reason_code == 'matched_event_team_mismatch'
    assert leg.settlement_explanation.settlement_reason_text == 'Matched event does not include player team'


def test_ambiguous_identity_review_explanation() -> None:
    leg = Leg(raw_text='Unknown Guy over 10.5 points', sport='NBA', market_type='player_points', player='Unknown Guy', direction='over', line=10.5, confidence=0.9, event_id='evt-1', identity_match_confidence='LOW')
    from app.grader import settle_leg

    graded = settle_leg(leg, DnpProvider())
    assert graded.settlement == 'unmatched'
    assert graded.settlement_explanation is not None
    assert graded.settlement_explanation.settlement_reason_code == 'identity_match_ambiguous'


def test_missing_stat_explanation() -> None:
    result = grade_text('Jokic over 24.5 points', provider=MissingStatProvider(), posted_at=datetime.fromisoformat('2026-03-07T18:15:00'))
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.settlement_reason_code == 'missing_stat_source'


def test_threes_explanation_uses_human_readable_reason() -> None:
    result = grade_text('Jamal Murray over 1.5 threes', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    leg = result.legs[0]
    assert leg.settlement == 'loss'
    assert leg.settlement_explanation is not None
    assert leg.settlement_explanation.normalized_market == 'player_threes'
    assert leg.settlement_explanation.actual_stat_value == 1.0
    assert leg.settlement_explanation.settlement_reason_text == '1.0 is below 1.5'


def test_low_confidence_single_candidate_uses_specific_review_text() -> None:
    leg = Leg(
        raw_text='shai gilly alexander over 2 points',
        sport='NBA',
        market_type='player_points',
        player='shai gilly alexander',
        direction='over',
        line=2.0,
        confidence=0.9,
        event_id='evt-1',
        identity_match_confidence='LOW',
        resolution_ambiguity_reason='player likely refers to Shai Gilgeous-Alexander, but identity confidence was not high enough to auto-resolve',
    )
    from app.grader import settle_leg

    graded = settle_leg(leg, DnpProvider())
    assert graded.review_reason_text == 'Review: player likely refers to Shai Gilgeous-Alexander, but identity confidence was not high enough to auto-resolve'
    assert graded.review_reason_text != 'Review: player/event validation failed'
