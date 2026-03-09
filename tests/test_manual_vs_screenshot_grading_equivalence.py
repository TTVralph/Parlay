from __future__ import annotations

from datetime import datetime, timezone, date

from app.grader import grade_text
from app.providers.base import EventInfo


class ComparisonProvider:
    def __init__(self) -> None:
        self.event = EventInfo(
            event_id='evt-nba-1',
            sport='NBA',
            home_team='Milwaukee Bucks',
            away_team='New York Knicks',
            start_time=datetime(2025, 11, 17, 1, 0, tzinfo=timezone.utc),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return self.event

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return self.event

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self.event]

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self.event]

    def get_event_info(self, event_id: str):
        return {'home_team': self.event.home_team, 'away_team': self.event.away_team}

    def get_event_status(self, event_id: str):
        return 'final'

    def did_player_appear(self, player: str, event_id: str | None = None):
        return True

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        key = (player.lower(), market_type)
        lookup = {
            ('giannis antetokounmpo', 'player_points'): 28.0,
            ('giannis antetokounmpo', 'player_rebounds'): 12.0,
            # Intentionally missing assists for Giannis PRA -> review.
        }
        return lookup.get(key)


SLIP_TEXT = '\n'.join(
    [
        'Giannis Antetokounmpo Over 20.5 Points',
        'Giannis Antetokounmpo Over 39.5 Pra',
    ]
)


def _snapshot(result):
    return [
        (
            leg.leg.raw_text,
            leg.settlement,
            leg.settlement_explanation.settlement_reason_code if leg.settlement_explanation else None,
            leg.review_reason,
            leg.review_reason_text,
            leg.debug_comparison.get('unmatched_reason_code'),
        )
        for leg in result.legs
    ]


def test_manual_and_screenshot_paths_are_equivalent_with_same_normalized_legs() -> None:
    provider = ComparisonProvider()
    manual = grade_text(
        SLIP_TEXT,
        provider=provider,
        bet_date=date(2025, 11, 17),
        code_path='manual_text_slip_grading',
    )
    screenshot = grade_text(
        SLIP_TEXT,
        provider=provider,
        bet_date=date(2025, 11, 17),
        code_path='screenshot_parse_grading',
    )

    assert _snapshot(manual) == _snapshot(screenshot)

    assert manual.legs[0].settlement == 'win'
    assert manual.legs[1].settlement == 'unmatched'
    assert manual.legs[1].settlement_explanation is not None
    assert manual.legs[1].settlement_explanation.settlement_reason_code == 'missing_stat_source'
    assert manual.legs[1].review_reason_text == 'Review: combo component stats incomplete'

    assert manual.legs[0].debug_comparison['input_source_path'] == 'manual_text'
    assert screenshot.legs[0].debug_comparison['input_source_path'] == 'screenshot'
