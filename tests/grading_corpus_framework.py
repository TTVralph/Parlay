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
    provider_factory: ProviderFactory | None = None
    include_historical: bool = False

    def generate(self) -> list[GoldenCase]:
        generated: list[GoldenCase] = []
        for player, stat_text, overall, settlement in self.checks:
            text = f'{player} {stat_text}'
            generated.append(
                GoldenCase(
                    name=f'{self.name_prefix}_{player.lower().replace(" ", "_")}_{stat_text.lower().replace(" ", "_")}',
                    text=text,
                    posted_at=self.posted_at,
                    include_historical=self.include_historical,
                    provider_factory=self.provider_factory,
                    overall=overall,
                    leg_expectations=(GoldenLegExpectation(settlement=settlement),),
                )
            )
        return generated


@dataclass(frozen=True)
class GoldenTextTemplate:
    name_prefix: str
    checks: tuple[tuple[str, str, str], ...]
    posted_at: datetime | None = None
    provider_factory: ProviderFactory | None = None
    include_historical: bool = False

    def generate(self) -> list[GoldenCase]:
        generated: list[GoldenCase] = []
        for idx, (text, overall, settlement) in enumerate(self.checks, start=1):
            generated.append(
                GoldenCase(
                    name=f'{self.name_prefix}_{idx:02d}',
                    text=text,
                    posted_at=self.posted_at,
                    include_historical=self.include_historical,
                    provider_factory=self.provider_factory,
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


class DeterministicPayloadVariationProvider:
    def resolve_player_event(self, player: str, as_of):
        from app.providers.base import EventInfo

        if player.lower() in {'mookie betts', 'aaron judge', 'juan soto', 'shohei ohtani'}:
            return EventInfo(
                event_id='evt-mlb-final',
                sport='MLB',
                home_team='Los Angeles Dodgers',
                away_team='New York Yankees',
                start_time=datetime.utcnow(),
            )
        if 'giddey' in player.lower():
            return EventInfo(
                event_id='evt-nba-live',
                sport='NBA',
                home_team='Chicago Bulls',
                away_team='Los Angeles Lakers',
                start_time=datetime.utcnow(),
            )
        return EventInfo(
            event_id='evt-nba-final',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.utcnow(),
        )

    def get_player_result_details(self, player: str, market_type: str, event_id=None):
        if market_type in {'player_pr', 'player_pa', 'player_ra', 'player_pra'}:
            return {'actual_value': 41.0, 'matched_boxscore_player_name': player}
        if market_type == 'player_total_bases':
            return {'actual_value': 3.0, 'matched_boxscore_player_name': player}
        return None

    def get_player_result(self, player: str, market_type: str, event_id=None):
        player_key = player.lower().strip()
        if market_type in {'player_points', 'player_rebounds', 'player_assists'}:
            if 'under' in player_key:
                return 1.0
            return 12.0
        if market_type == 'player_total_bases':
            return 3.0
        if market_type == 'player_hits':
            return 2.0
        if market_type == 'player_strikeouts':
            return 8.0
        return 10.0

    def get_event_status(self, event_id: str):
        statuses = {
            'evt-nba-final': 'FINAL',
            'evt-mlb-final': 'completed',
            'evt-nba-live': 'in_progress',
        }
        return statuses.get(event_id, 'final')

    def did_player_appear(self, player: str, event_id=None):
        return True


class AmbiguousEventProvider:
    def resolve_player_event_candidates(self, player: str, as_of, include_historical=False):
        from app.providers.base import EventInfo

        return [
            EventInfo(
                event_id='evt-amb-1',
                sport='NBA',
                home_team='Oklahoma City Thunder',
                away_team='Denver Nuggets',
                start_time=datetime.fromisoformat('2026-03-07T19:00:00'),
            ),
            EventInfo(
                event_id='evt-amb-2',
                sport='NBA',
                home_team='Oklahoma City Thunder',
                away_team='Denver Nuggets',
                start_time=datetime.fromisoformat('2026-03-09T19:00:00'),
            ),
        ]

    def get_player_result(self, player: str, market_type: str, event_id=None):
        return 10.0

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

    nba_combo_expansion = GoldenTemplate(
        name_prefix='nba_combo_expanded',
        posted_at=datetime.fromisoformat('2026-03-07T19:00:00'),
        provider_factory=DeterministicPayloadVariationProvider,
        checks=(
            ('Nikola Jokic', 'over 30.5 PR', 'lost', 'loss'),
            ('Nikola Jokic', 'over 29.5 PA', 'lost', 'loss'),
            ('Nikola Jokic', 'over 17.5 RA', 'cashed', 'win'),
            ('Nikola Jokic', 'over 38.5 PRA', 'lost', 'loss'),
            ('Jayson Tatum', 'over 29.5 PR', 'lost', 'loss'),
            ('Jayson Tatum', 'over 28.5 PA', 'lost', 'loss'),
            ('Jayson Tatum', 'over 14.5 RA', 'cashed', 'win'),
            ('Jayson Tatum', 'over 34.5 PRA', 'cashed', 'win'),
            ('Luka Doncic', 'over 31.5 PR', 'needs_review', 'unmatched'),
            ('Luka Doncic', 'over 32.5 PA', 'needs_review', 'unmatched'),
            ('Luka Doncic', 'over 17.5 RA', 'needs_review', 'unmatched'),
            ('Luka Doncic', 'over 42.5 PRA', 'needs_review', 'unmatched'),
            ('Devin Booker', 'over 28.5 PR', 'needs_review', 'unmatched'),
            ('Devin Booker', 'over 29.5 PA', 'needs_review', 'unmatched'),
            ('Devin Booker', 'over 13.5 RA', 'needs_review', 'unmatched'),
            ('Devin Booker', 'over 37.5 PRA', 'needs_review', 'unmatched'),
            ('Anthony Edwards', 'over 26.5 PR', 'needs_review', 'unmatched'),
            ('Anthony Edwards', 'over 27.5 PA', 'needs_review', 'unmatched'),
            ('Anthony Edwards', 'over 11.5 RA', 'needs_review', 'unmatched'),
            ('Anthony Edwards', 'over 33.5 PRA', 'needs_review', 'unmatched'),
        ),
    )

    mlb_total_bases_template = GoldenTextTemplate(
        name_prefix='mlb_total_bases_derived',
        provider_factory=DeterministicPayloadVariationProvider,
        checks=(
            ('Mookie Betts over 1.5 total bases', 'needs_review', 'unmatched'),
            ('Mookie Betts over 1.5 TB', 'needs_review', 'unmatched'),
            ('Mookie Betts over 1.5 bases', 'needs_review', 'unmatched'),
            ('Aaron Judge over 1.5 total bases', 'cashed', 'win'),
            ('Aaron Judge over 2.5 total bases', 'cashed', 'win'),
            ('Juan Soto over 1.5 total bases', 'needs_review', 'unmatched'),
            ('Shohei Ohtani over 1.5 total bases', 'cashed', 'win'),
            ('Mookie Betts under 4.5 total bases', 'needs_review', 'unmatched'),
            ('Aaron Judge under 4.5 TB', 'cashed', 'win'),
            ('Juan Soto under 5.5 total bases', 'needs_review', 'unmatched'),
            ('Shohei Ohtani under 5.5 total bases', 'cashed', 'win'),
            ('Mookie Betts over 3.5 total bases', 'needs_review', 'unmatched'),
            ('Aaron Judge over 3.5 total bases', 'lost', 'loss'),
            ('Juan Soto over 3.5 total bases', 'needs_review', 'unmatched'),
            ('Shohei Ohtani over 3.5 total bases', 'lost', 'loss'),
        ),
    )

    ambiguous_resolution_template = GoldenTextTemplate(
        name_prefix='ambiguous_player_resolution',
        provider_factory=AmbiguousEventProvider,
        checks=(
            ('J Williams over 4.5 assists', 'needs_review', 'unmatched'),
            ('C Johnson over 1.5 threes', 'needs_review', 'unmatched'),
            ('M Brown over 2.5 rebounds', 'needs_review', 'unmatched'),
            ('J Smith over 10.5 points', 'needs_review', 'unmatched'),
            ('A Thompson over 5.5 assists', 'needs_review', 'unmatched'),
            ('N Reid over 10.5 points', 'needs_review', 'unmatched'),
            ('J Green over 1.5 threes', 'needs_review', 'unmatched'),
            ('A Gordon over 14.5 points', 'needs_review', 'unmatched'),
            ('K Porter over 8.5 points', 'needs_review', 'unmatched'),
            ('J Murray over 2.5 threes', 'needs_review', 'unmatched'),
        ),
    )

    missing_bet_date_template = GoldenTextTemplate(
        name_prefix='missing_bet_date_review',
        checks=(
            ('Shai Gilgeous-Alexander over 6.5 assists', 'cashed', 'win'),
            ('Jamal Murray over 2.5 threes', 'needs_review', 'unmatched'),
            ('Nikola Jokic over 26.5 points', 'needs_review', 'unmatched'),
            ('LeBron James over 24.5 points', 'needs_review', 'unmatched'),
            ('Stephen Curry over 4.5 threes', 'needs_review', 'unmatched'),
            ('Jayson Tatum over 8.5 rebounds', 'lost', 'loss'),
            ('Jaylen Brown over 1.5 threes', 'needs_review', 'unmatched'),
            ('Luka Doncic over 31.5 points', 'needs_review', 'unmatched'),
            ('Anthony Edwards over 24.5 points', 'needs_review', 'unmatched'),
            ('Kevin Durant over 25.5 points', 'needs_review', 'unmatched'),
        ),
    )

    provider_payload_variation_template = GoldenTextTemplate(
        name_prefix='provider_payload_variation',
        provider_factory=DeterministicPayloadVariationProvider,
        checks=(
            ('Nikola Jokic over 24.5 points', 'lost', 'loss'),
            ('Nikola Jokic over 8.5 assists', 'cashed', 'win'),
            ('Nikola Jokic under 40.5 points', 'cashed', 'win'),
            ('Nikola Jokic over 45.5 points', 'lost', 'loss'),
            ('Nikola Jokic over 39.5 PRA', 'lost', 'loss'),
            ('Nikola Jokic over 39.5 PR', 'lost', 'loss'),
            ('Nikola Jokic over 39.5 PA', 'lost', 'loss'),
            ('Nikola Jokic over 39.5 RA', 'lost', 'loss'),
            ('Josh Giddey over 8.5 assists', 'pending', 'live'),
            ('Mookie Betts over 1.5 total bases', 'needs_review', 'unmatched'),
        ),
    )

    multi_leg_mixed_state_cases: list[GoldenCase] = [
        GoldenCase(
            name='multi_leg_mixed_states_win_live_loss',
            text='Josh Giddey over 8.5 assists\nNikola Jokic over 35.5 points\nMookie Betts over 1.5 total bases',
            overall='needs_review',
            provider_factory=DeterministicPayloadVariationProvider,
            leg_expectations=(
                GoldenLegExpectation('live'),
                GoldenLegExpectation('loss'),
                GoldenLegExpectation('unmatched'),
            ),
        ),
        GoldenCase(
            name='multi_leg_mixed_states_all_win_except_live',
            text='Josh Giddey over 8.5 assists\nNikola Jokic over 24.5 points\nMookie Betts over 1.5 total bases',
            overall='needs_review',
            provider_factory=DeterministicPayloadVariationProvider,
            leg_expectations=(
                GoldenLegExpectation('live'),
                GoldenLegExpectation('loss'),
                GoldenLegExpectation('unmatched'),
            ),
        ),
        GoldenCase(
            name='multi_leg_mixed_states_with_void_provider',
            text='Nikola Jokic over 8.5 points\nJosh Giddey over 8.5 assists\nNikola Jokic over 12.5 points',
            overall='lost',
            provider_factory=LiveProvider,
            leg_expectations=(
                GoldenLegExpectation('win'),
                GoldenLegExpectation('live'),
                GoldenLegExpectation('loss'),
            ),
        ),
        GoldenCase(
            name='multi_leg_mixed_states_two_live_one_loss',
            text='Josh Giddey over 8.5 assists\nJosh Giddey under 12.5 assists\nNikola Jokic over 12.5 points',
            overall='lost',
            provider_factory=LiveProvider,
            leg_expectations=(
                GoldenLegExpectation('live'),
                GoldenLegExpectation('live'),
                GoldenLegExpectation('loss'),
            ),
        ),
        GoldenCase(
            name='multi_leg_mixed_states_live_kill_path',
            text='Josh Giddey under 8.5 assists\nNikola Jokic over 12.5 points\nJosh Giddey over 8.5 assists',
            overall='lost',
            provider_factory=LiveKillProvider,
            leg_expectations=(
                GoldenLegExpectation('loss', kill_moment=True),
                GoldenLegExpectation('loss'),
                GoldenLegExpectation('live'),
            ),
        ),
    ]

    corpus = [
        *base_cases,
        *combo_template.generate(),
        *nba_combo_expansion.generate(),
        *mlb_total_bases_template.generate(),
        *ambiguous_resolution_template.generate(),
        *missing_bet_date_template.generate(),
        *provider_payload_variation_template.generate(),
        *multi_leg_mixed_state_cases,
    ]
    assert len(corpus) == 95, f'Expected 95 expanded golden cases, found {len(corpus)}'
    return corpus
