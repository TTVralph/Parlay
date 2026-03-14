from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from app.grader import grade_text
from app.models import GradeResponse


ProviderFactory = Callable[[], object]


@dataclass(frozen=True)
class GoldenLegExpectation:
    settlement: str
    event_id: str | None = None
    kill_moment: bool | None = None
    normalized_market: str | None = None


@dataclass(frozen=True)
class GoldenCase:
    name: str
    text: str
    overall: str
    leg_expectations: tuple[GoldenLegExpectation, ...]
    posted_at: datetime | None = None
    include_historical: bool = False
    provider_factory: ProviderFactory | None = None
    expected_reason_contains: str | None = None


@dataclass(frozen=True)
class GoldenTemplate:
    name_prefix: str
    posted_at: datetime
    checks: tuple[tuple[str, str, str, str], ...]

    def generate(self) -> list[GoldenCase]:
        generated: list[GoldenCase] = []
        for player, stat_text, overall, settlement in self.checks:
            text = f'{player} {stat_text}'
            generated.append(
                GoldenCase(
                    name=f'{self.name_prefix}_{player.lower().replace(" ", "_")}_{stat_text.lower().replace(" ", "_")}',
                    text=text,
                    posted_at=self.posted_at,
                    overall=overall,
                    leg_expectations=(GoldenLegExpectation(settlement=settlement),),
                )
            )
        return generated


class VoidProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo

        return EventInfo(
            event_id='evt-void',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.utcnow(),
        )

    def get_player_result(self, player: str, market_type: str, event_id=None):
        return None

    def get_event_status(self, event_id: str):
        return 'final'

    def did_player_appear(self, player: str, event_id=None):
        return False


class LiveProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo

        if 'giddey' in player.lower():
            return EventInfo(
                event_id='evt-live',
                sport='NBA',
                home_team='Los Angeles Lakers',
                away_team='Chicago Bulls',
                start_time=datetime.utcnow(),
            )
        return EventInfo(
            event_id='evt-final',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.utcnow(),
        )

    def get_player_result(self, player: str, market_type: str, event_id=None):
        if event_id == 'evt-live':
            return 0.0
        return 10.0

    def get_event_status(self, event_id: str):
        return 'live' if event_id == 'evt-live' else 'final'


class LiveKillProvider(LiveProvider):
    def get_player_result(self, player: str, market_type: str, event_id=None):
        if event_id == 'evt-live':
            return 10.0
        return super().get_player_result(player, market_type, event_id=event_id)


class MatchedBoxScoreProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo

        return EventInfo(
            event_id='evt-boxscore',
            sport='NBA',
            home_team='Golden State Warriors',
            away_team='Boston Celtics',
            start_time=datetime.utcnow(),
        )

    def get_player_result_details(self, player: str, market_type: str, event_id=None):
        return {'actual_value': 6.0, 'matched_boxscore_player_name': 'Draymond Green'}

    def get_player_result(self, player: str, market_type: str, event_id=None):
        return 6.0

    def get_event_status(self, event_id: str):
        return 'final'


def run_case(case: GoldenCase) -> GradeResponse:
    kwargs: dict[str, object] = {
        'include_historical': case.include_historical,
    }
    if case.posted_at:
        kwargs['posted_at'] = case.posted_at
    if case.provider_factory is not None:
        kwargs['provider'] = case.provider_factory()

    return grade_text(case.text, **kwargs)


def assert_case(case: GoldenCase, result: GradeResponse) -> None:
    assert result.overall == case.overall, case.name
    assert len(result.legs) == len(case.leg_expectations), case.name
    if case.expected_reason_contains:
        joined = ' '.join((item.review_reason or '') + ' ' + (item.explanation_reason or '') for item in result.legs)
        assert case.expected_reason_contains in joined, case.name

    for idx, expected_leg in enumerate(case.leg_expectations):
        actual_leg = result.legs[idx]
        assert actual_leg.settlement == expected_leg.settlement, f'{case.name} leg {idx}'
        if expected_leg.event_id is not None:
            assert actual_leg.leg.event_id == expected_leg.event_id, f'{case.name} leg {idx}'
        if expected_leg.kill_moment is not None:
            assert actual_leg.kill_moment is expected_leg.kill_moment, f'{case.name} leg {idx}'
        if expected_leg.normalized_market is not None:
            assert actual_leg.normalized_market == expected_leg.normalized_market, f'{case.name} leg {idx}'


def high_value_case_corpus() -> list[GoldenCase]:
    base_cases: list[GoldenCase] = [
        GoldenCase(
            name='sample_parlay_mixed_results',
            text='Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='lost',
            leg_expectations=(
                GoldenLegExpectation('win', event_id='nba-2026-03-07-den-lal'),
                GoldenLegExpectation('win', event_id='nba-2026-03-07-den-lal'),
                GoldenLegExpectation('loss', event_id='nba-2026-03-07-den-lal'),
            ),
        ),
        GoldenCase(
            name='jokic_points_over_wins',
            text='Jokic over 24.5 points',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', normalized_market='Points'),),
        ),
        GoldenCase(
            name='jokic_points_under_loses_with_kill_moment',
            text='Jokic under 24.5 points',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='lost',
            leg_expectations=(GoldenLegExpectation('loss', kill_moment=True),),
        ),
        GoldenCase(
            name='cooper_flagg_pra_combo_win',
            text='Cooper Flagg Over 25.5 PRA',
            posted_at=datetime.fromisoformat('2026-03-06T00:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', normalized_market='PRA'),),
        ),
        GoldenCase(
            name='threes_alias_market_loss',
            text='Nikola Jokic Over 1.5 Threes Made',
            posted_at=datetime.fromisoformat('2026-03-06T00:00:00'),
            overall='lost',
            leg_expectations=(GoldenLegExpectation('loss', normalized_market='Threes Made'),),
        ),
        GoldenCase(
            name='team_moneyline_settles',
            text='Denver ML',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', normalized_market='Moneyline'),),
        ),
        GoldenCase(
            name='missing_date_ambiguous_needs_review',
            text='Jamal Murray over 2.5 threes',
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'),),
            expected_reason_contains='Multiple plausible games were found',
        ),
        GoldenCase(
            name='historical_scan_ambiguous_review',
            text='Jokic over 24.5 points',
            posted_at=datetime.fromisoformat('2026-03-01T00:00:00'),
            include_historical=True,
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'),),
            expected_reason_contains='Multiple plausible games were found',
        ),
        GoldenCase(
            name='unparseable_text_needs_review',
            text='Leg A\nLeg B',
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'), GoldenLegExpectation('unmatched')),
            expected_reason_contains='Could not parse stat type',
        ),
        GoldenCase(
            name='single_game_selection_by_bet_date',
            text='Jamal Murray over 2.5 threes',
            posted_at=datetime.fromisoformat('2026-03-09T00:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', event_id='nba-2026-03-09-okc-den'),),
        ),
        GoldenCase(
            name='void_player_dnp',
            text='Nikola Jokic over 8.5 points',
            overall='needs_review',
            provider_factory=VoidProvider,
            leg_expectations=(GoldenLegExpectation('void'),),
        ),
        GoldenCase(
            name='live_leg_pending',
            text='Josh Giddey over 8.5 assists',
            overall='pending',
            provider_factory=LiveProvider,
            leg_expectations=(GoldenLegExpectation('live'),),
        ),
        GoldenCase(
            name='live_under_kill_moment_loss',
            text='Josh Giddey under 8.5 assists',
            overall='lost',
            provider_factory=LiveKillProvider,
            leg_expectations=(GoldenLegExpectation('loss', kill_moment=True),),
        ),
        GoldenCase(
            name='mixed_live_and_final_can_be_lost',
            text='Josh Giddey over 8.5 assists\nNikola Jokic over 12.5 points',
            overall='lost',
            provider_factory=LiveProvider,
            leg_expectations=(GoldenLegExpectation('live'), GoldenLegExpectation('loss')),
        ),
        GoldenCase(
            name='boxscore_name_match_integration',
            text='Draymond Green over 4.5 assists',
            overall='cashed',
            provider_factory=MatchedBoxScoreProvider,
            leg_expectations=(GoldenLegExpectation('win', normalized_market='Assists'),),
        ),
        GoldenCase(
            name='unsupported_steals_market_review',
            text='Jokic over 0.5 steals',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'),),
        ),
        GoldenCase(
            name='unsupported_blocks_market_review',
            text='Jokic over 0.5 blocks',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'),),
        ),
        GoldenCase(
            name='unsupported_turnovers_market_review',
            text='Jokic under 3.5 turnovers',
            posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
            overall='needs_review',
            leg_expectations=(GoldenLegExpectation('unmatched'),),
        ),
        GoldenCase(
            name='alias_name_shai_settles',
            text='SGA over 6 assists',
            posted_at=datetime.fromisoformat('2026-03-09T00:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', event_id='nba-2026-03-09-okc-den'),),
        ),
        GoldenCase(
            name='canonical_name_shai_settles',
            text='Shai Gilgeous-Alexander over 6 assists',
            posted_at=datetime.fromisoformat('2026-03-09T00:00:00'),
            overall='cashed',
            leg_expectations=(GoldenLegExpectation('win', event_id='nba-2026-03-09-okc-den'),),
        ),
    ]

    combo_template = GoldenTemplate(
        name_prefix='combo_market',
        posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
        checks=(
            ('Jokic', 'over 34.5 PR', 'cashed', 'win'),
            ('Jokic', 'over 34.5 PA', 'cashed', 'win'),
            ('Jokic', 'over 15.5 RA', 'cashed', 'win'),
            ('Jokic', 'over 36.5 PRA', 'cashed', 'win'),
            ('Jokic', 'over 9.5 rebounds', 'cashed', 'win'),
        ),
    )

    corpus = [*base_cases, *combo_template.generate()]
    assert len(corpus) == 25, f'Expected 25 first-pass golden cases, found {len(corpus)}'
    return corpus
