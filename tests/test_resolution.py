from datetime import date, datetime, timezone

from app.grader import grade_text
from app.models import Leg
from app.providers.base import EventInfo, TeamResult
from app.providers.sample_provider import SampleResultsProvider
from app.resolver import resolve_leg_events


def test_date_resolution_uses_posted_time_for_denver_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts\nDenver ML',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-07T18:15:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[1].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'


def test_date_resolution_switches_to_later_jokic_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-09T18:00:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'
    assert result.legs[0].settlement == 'loss'


class OpponentFilterProvider:
    def resolve_team_event(self, team: str, as_of: datetime | None):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None):
        if player != 'Draymond':
            return []
        return [
            EventInfo(event_id='evt-bos-gsw', sport='NBA', home_team='Boston Celtics', away_team='Golden State Warriors', start_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            EventInfo(event_id='evt-okc-gsw', sport='NBA', home_team='Oklahoma City Thunder', away_team='Golden State Warriors', start_time=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ]

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_opponent_context_filters_ambiguous_player_event_candidates() -> None:
    provider = OpponentFilterProvider()
    leg = Leg(raw_text='Draymond 5+ Assists Vs Thunder', sport='NBA', market_type='player_assists', player='Draymond', direction='over', line=4.5, confidence=0.82, notes=['Opponent context: Oklahoma City Thunder'])
    resolved = resolve_leg_events([leg], provider, posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert resolved[0].event_id == 'evt-okc-gsw'


class HistoricalOnlyProvider:
    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team != 'Denver Nuggets':
            return []
        if not include_historical:
            return []
        return [EventInfo(event_id='hist-den', sport='NBA', home_team='Denver Nuggets', away_team='Los Angeles Lakers', start_time=datetime(2024, 1, 1, tzinfo=timezone.utc))]

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def get_team_result(self, team: str, event_id: str | None = None):
        if event_id != 'hist-den':
            return None
        event = EventInfo(event_id='hist-den', sport='NBA', home_team='Denver Nuggets', away_team='Los Angeles Lakers', start_time=datetime(2024, 1, 1, tzinfo=timezone.utc))
        return TeamResult(event=event, moneyline_win=True, home_score=100, away_score=90)

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_grade_text_falls_back_to_historical_when_recent_empty() -> None:
    provider = HistoricalOnlyProvider()
    result = grade_text('Denver ML', provider=provider, posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert result.legs[0].leg.event_id == 'hist-den'


def test_slip_date_exact_match_denver_on_2026_03_06_resolves_knicks() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Denver ML',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-06T00:00:00'),
        include_historical=True,
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-06-den-nyk'


def test_slip_date_exact_match_denver_on_2026_03_05_resolves_lakers() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Denver ML',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-05T00:00:00'),
        include_historical=True,
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-05-den-lal'


def test_slip_date_never_matches_previous_day_event() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Denver ML\nJokic over 24.5 points',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-06T00:00:00'),
        include_historical=True,
    )

    assert all(item.leg.event_id == 'nba-2026-03-06-den-nyk' for item in result.legs)
    assert all(item.leg.event_id != 'nba-2026-03-05-den-lal' for item in result.legs)


class LockedEventNoPlayerStatsProvider:
    def __init__(self) -> None:
        self._event = EventInfo(
            event_id='nba-2026-02-11-mem-den',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Memphis Grizzlies',
            start_time=datetime.fromisoformat('2026-02-12T02:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return self._event if team in {self._event.home_team, self._event.away_team} else None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return self._event if player in {'Nikola Jokic', 'Jamal Murray'} else None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self._event] if team in {self._event.home_team, self._event.away_team} else []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [self._event] if player in {'Nikola Jokic', 'Jamal Murray'} else []

    def get_team_result(self, team: str, event_id: str | None = None):
        if event_id != self._event.event_id:
            return None
        return TeamResult(
            event=self._event,
            moneyline_win=(team == 'Denver Nuggets'),
            home_score=122,
            away_score=116,
        )

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None

    def get_event_status(self, event_id: str):
        if event_id != self._event.event_id:
            return None
        return 'final'


def test_slip_date_team_leg_locks_event_and_ml_settles_when_player_stats_missing() -> None:
    provider = LockedEventNoPlayerStatsProvider()
    result = grade_text(
        'Jokic over 24.5 points\nMurray over 2.5 threes\nDenver ML',
        provider=provider,
        posted_at=date.fromisoformat('2026-02-11'),
        include_historical=True,
    )

    assert all(item.leg.event_id == 'nba-2026-02-11-mem-den' for item in result.legs)
    assert result.legs[2].settlement == 'win'
    assert result.legs[0].settlement == 'unmatched'
    assert result.legs[1].settlement == 'unmatched'
    assert result.overall == 'needs_review'


class PlayerTeamDateFilterProvider:
    def __init__(self) -> None:
        self._good_event = EventInfo(
            event_id='nba-2026-03-07-lac-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )
        self._bad_event = EventInfo(
            event_id='nba-2026-03-07-uta-mil',
            sport='NBA',
            home_team='Milwaukee Bucks',
            away_team='Utah Jazz',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player in {'Cam Spencer', 'Scotty Pippen Jr.'}:
            return [self._good_event, self._bad_event]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player in {'Cam Spencer', 'Scotty Pippen Jr.'}:
            return 'Memphis Grizzlies'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_cam_spencer_never_resolves_to_jazz_at_bucks_on_slip_date() -> None:
    provider = PlayerTeamDateFilterProvider()
    result = grade_text(
        'Cam Spencer over 9.5 points',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    assert result.legs[0].leg.event_id in {'nba-2026-03-07-lac-mem', None}
    assert result.legs[0].leg.event_id != 'nba-2026-03-07-uta-mil'


def test_scotty_pippen_jr_resolves_to_clippers_at_grizzlies_on_slip_date() -> None:
    provider = PlayerTeamDateFilterProvider()
    result = grade_text(
        'Scotty Pippen Jr. over 5.5 assists',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    assert result.legs[0].leg.event_id == 'nba-2026-03-07-lac-mem'
    assert result.legs[0].leg.event_label == 'LA Clippers @ Memphis Grizzlies'


class PlayerTeamCandidateVisibilityProvider:
    def __init__(self) -> None:
        self._mem_event_a = EventInfo(
            event_id='nba-2026-03-07-lac-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )
        self._mem_event_b = EventInfo(
            event_id='nba-2026-03-07-mem-por',
            sport='NBA',
            home_team='Portland Trail Blazers',
            away_team='Memphis Grizzlies',
            start_time=datetime.fromisoformat('2026-03-08T03:00:00+00:00'),
        )
        self._wrong_event = EventInfo(
            event_id='nba-2026-03-07-uta-mil',
            sport='NBA',
            home_team='Milwaukee Bucks',
            away_team='Utah Jazz',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Scotty Pippen Jr.':
            return [self._mem_event_a, self._mem_event_b, self._wrong_event]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Scotty Pippen Jr.':
            return 'Memphis Grizzlies'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_player_candidate_games_hide_non_team_events() -> None:
    provider = PlayerTeamCandidateVisibilityProvider()
    result = grade_text(
        'Scotty Pippen over 5.5 assists',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    leg = result.legs[0].leg
    assert leg.event_id is None
    candidate_ids = {item['event_id'] for item in leg.event_candidates}
    assert candidate_ids == {'nba-2026-03-07-lac-mem', 'nba-2026-03-07-mem-por'}
    assert 'nba-2026-03-07-uta-mil' not in candidate_ids


class IndependentLegResolutionProvider:
    def __init__(self) -> None:
        self._events = {
            'nba-2026-03-09-okc-den': EventInfo(
                event_id='nba-2026-03-09-okc-den',
                sport='NBA',
                home_team='Oklahoma City Thunder',
                away_team='Denver Nuggets',
                start_time=datetime.fromisoformat('2026-03-09T20:00:00+00:00'),
            ),
            'nba-2026-03-09-bos-gsw': EventInfo(
                event_id='nba-2026-03-09-bos-gsw',
                sport='NBA',
                home_team='Boston Celtics',
                away_team='Golden State Warriors',
                start_time=datetime.fromisoformat('2026-03-09T22:00:00+00:00'),
            ),
            'nba-2026-03-07-mem-lal': EventInfo(
                event_id='nba-2026-03-07-mem-lal',
                sport='NBA',
                home_team='Memphis Grizzlies',
                away_team='Los Angeles Lakers',
                start_time=datetime.fromisoformat('2026-03-07T21:00:00+00:00'),
            ),
        }

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Nikola Jokic':
            return [self._events['nba-2026-03-09-okc-den'], self._events['nba-2026-03-09-bos-gsw']]
        if player == 'Stephen Curry':
            return [self._events['nba-2026-03-09-bos-gsw'], self._events['nba-2026-03-09-okc-den']]
        if player == 'LeBron James':
            return [self._events['nba-2026-03-07-mem-lal']]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return {
            'Nikola Jokic': 'Denver Nuggets',
            'Stephen Curry': 'Golden State Warriors',
            'LeBron James': 'Los Angeles Lakers',
        }.get(player)

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_same_date_legs_can_resolve_to_different_events() -> None:
    provider = IndependentLegResolutionProvider()
    result = grade_text(
        'Jokic over 24.5 points\nCurry over 4.5 threes',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-09'),
        include_historical=True,
    )

    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'
    assert result.legs[1].leg.event_id == 'nba-2026-03-09-bos-gsw'


def test_different_date_legs_still_resolve_independently() -> None:
    provider = IndependentLegResolutionProvider()
    legs = [
        Leg(
            raw_text='Jokic over 24.5 points vs Thunder',
            sport='NBA',
            market_type='player_points',
            player='Nikola Jokic',
            direction='over',
            line=24.5,
            confidence=0.9,
            notes=['Opponent context: Oklahoma City Thunder'],
        ),
        Leg(
            raw_text='LeBron over 24.5 points vs Grizzlies',
            sport='NBA',
            market_type='player_points',
            player='LeBron James',
            direction='over',
            line=24.5,
            confidence=0.9,
            notes=['Opponent context: Memphis Grizzlies'],
        ),
    ]

    resolved = resolve_leg_events(legs, provider, posted_at=None, include_historical=True)

    assert resolved[0].event_id == 'nba-2026-03-09-okc-den'
    assert resolved[1].event_id == 'nba-2026-03-07-mem-lal'


class ScottyPippenAliasSettlementProvider:
    def __init__(self) -> None:
        self._good_event = EventInfo(
            event_id='nba-2026-03-07-lac-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )
        self._other_mem_event = EventInfo(
            event_id='nba-2026-03-07-sas-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='San Antonio Spurs',
            start_time=datetime.fromisoformat('2026-03-08T03:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Cam Spencer':
            return [self._good_event]
        if player == 'Scotty Pippen Jr.':
            return [self._other_mem_event, self._good_event]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player in {'Cam Spencer', 'Scotty Pippen Jr.'}:
            return 'Memphis Grizzlies'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        if player == 'Cam Spencer' and market_type == 'player_points' and event_id == self._good_event.event_id:
            return 10.0
        if player == 'Scotty Pippen Jr.' and market_type == 'player_assists' and event_id == self._good_event.event_id:
            return 3.0
        return None


def test_scotty_pippen_alias_under_assists_settles_win_on_2026_03_07() -> None:
    provider = ScottyPippenAliasSettlementProvider()
    result = grade_text(
        'Cam Spencer over 9.5 points\nScotty Pippen Under 4.5 Assists',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    assert result.overall == 'cashed'
    assert result.legs[1].leg.player == 'Scotty Pippen Jr.'
    assert result.legs[1].leg.event_id == 'nba-2026-03-07-lac-mem'
    assert result.legs[1].leg.event_label == 'LA Clippers @ Memphis Grizzlies'
    assert result.legs[1].settlement == 'win'
    assert result.legs[1].actual_value == 3.0

class TeamDateHintProvider:
    def __init__(self) -> None:
        self._evt_target = EventInfo(
            event_id='nba-2026-03-07-lac-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )
        self._evt_other_day = EventInfo(
            event_id='nba-2026-03-08-sas-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='San Antonio Spurs',
            start_time=datetime.fromisoformat('2026-03-09T01:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team == 'Memphis Grizzlies':
            return [self._evt_target]
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player in {'Cam Spencer', 'Scotty Pippen Jr.'}:
            return [self._evt_other_day, self._evt_target]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player in {'Cam Spencer', 'Scotty Pippen Jr.'}:
            return 'Memphis Grizzlies'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_player_team_date_filter_auto_resolves_single_remaining_candidate() -> None:
    provider = TeamDateHintProvider()
    result = grade_text(
        'Cam Spencer over 9.5 points',
        provider=provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    assert result.legs[0].leg.event_id == 'nba-2026-03-07-lac-mem'
    assert result.legs[0].leg.event_candidates == []


def test_resolved_team_date_context_hints_following_player_leg() -> None:
    provider = TeamDateHintProvider()
    legs = [
        Leg(
            raw_text='Memphis ML',
            sport='NBA',
            market_type='moneyline',
            team='Memphis Grizzlies',
            confidence=0.9,
            notes=[],
        ),
        Leg(
            raw_text='Scotty Pippen under 4.5 assists',
            sport='NBA',
            market_type='player_assists',
            player='Scotty Pippen Jr.',
            direction='under',
            line=4.5,
            confidence=0.9,
            notes=[],
        ),
    ]

    resolved = resolve_leg_events(
        legs,
        provider,
        posted_at=date.fromisoformat('2026-03-07'),
        include_historical=True,
    )

    assert resolved[0].event_id == 'nba-2026-03-07-lac-mem'
    assert resolved[1].event_id == 'nba-2026-03-07-lac-mem'


class TeamScopedCandidateProvider:
    def __init__(self) -> None:
        self._mem_good = EventInfo(
            event_id='nba-2026-03-07-lac-mem',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-07T20:00:00'),
        )
        self._mem_other = EventInfo(
            event_id='nba-2026-03-09-mem-dal',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='Dallas Mavericks',
            start_time=datetime.fromisoformat('2026-03-09T20:00:00'),
        )
        self._uta_good = EventInfo(
            event_id='nba-2026-03-07-uta-por',
            sport='NBA',
            home_team='Utah Jazz',
            away_team='Portland Trail Blazers',
            start_time=datetime.fromisoformat('2026-03-07T20:00:00'),
        )
        self._unrelated = EventInfo(
            event_id='nba-2026-03-07-lal-den',
            sport='NBA',
            home_team='Los Angeles Lakers',
            away_team='Denver Nuggets',
            start_time=datetime.fromisoformat('2026-03-07T21:00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Cam Spencer':
            return [self._mem_good, self._mem_other, self._unrelated]
        if player == 'Keyonte George':
            return [self._uta_good, self._unrelated]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return {
            'Cam Spencer': 'Memphis Grizzlies',
            'Keyonte George': 'Utah Jazz',
        }.get(player)

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_cam_spencer_candidates_include_only_memphis_games() -> None:
    provider = TeamScopedCandidateProvider()
    legs = [
        Leg(
            raw_text='Cam Spencer over 9.5 points',
            sport='NBA',
            market_type='player_points',
            player='Cam Spencer',
            line=9.5,
            direction='over',
            confidence=0.9,
            notes=[],
        ),
    ]

    resolved = resolve_leg_events(legs, provider, posted_at=None, include_historical=True)
    candidate_ids = {item['event_id'] for item in resolved[0].event_candidates}
    assert candidate_ids == {'nba-2026-03-07-lac-mem', 'nba-2026-03-09-mem-dal'}


def test_keyonte_george_candidates_include_only_utah_games() -> None:
    provider = TeamScopedCandidateProvider()
    legs = [
        Leg(
            raw_text='Keyonte George over 5.5 assists',
            sport='NBA',
            market_type='player_assists',
            player='Keyonte George',
            line=5.5,
            direction='over',
            confidence=0.9,
            notes=[],
        ),
    ]

    resolved = resolve_leg_events(legs, provider, posted_at=None, include_historical=True)
    assert resolved[0].event_id == 'nba-2026-03-07-uta-por'
    assert resolved[0].event_candidates == []
