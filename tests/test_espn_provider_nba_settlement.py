from __future__ import annotations

from datetime import datetime, timezone

from app.providers.espn_provider import ESPNNBAResultsProvider


class StubProvider(ESPNNBAResultsProvider):
    def __init__(self) -> None:
        super().__init__()
        self._event_id = 'evt-1'
        self._event_date = '2026-01-01T00:00:00Z'

    def _candidate_days(self, as_of: datetime | None) -> list[str]:
        return ['20260101']

    def _scoreboard_for_day(self, day_key: str):
        return {
            'events': [
                {
                    'id': self._event_id,
                    'date': self._event_date,
                    'competitions': [
                        {
                            'status': {'type': {'completed': True, 'state': 'post'}},
                            'competitors': [
                                {
                                    'homeAway': 'home',
                                    'score': '110',
                                    'team': {
                                        'displayName': 'Oklahoma City Thunder',
                                        'shortDisplayName': 'Thunder',
                                        'name': 'Thunder',
                                        'abbreviation': 'OKC',
                                        'location': 'Oklahoma City',
                                    },
                                },
                                {
                                    'homeAway': 'away',
                                    'score': '115',
                                    'team': {
                                        'displayName': 'Denver Nuggets',
                                        'shortDisplayName': 'Nuggets',
                                        'name': 'Nuggets',
                                        'abbreviation': 'DEN',
                                        'location': 'Denver',
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        }

    def _summary(self, event_id: str):
        assert event_id == self._event_id
        return {
            'header': {
                'competitions': [
                    {
                        'date': self._event_date,
                        'status': {'type': {'completed': True, 'state': 'post'}},
                        'competitors': [
                            {
                                'homeAway': 'home',
                                'score': '110',
                                'team': {'displayName': 'Oklahoma City Thunder', 'location': 'Oklahoma City', 'name': 'Thunder'},
                            },
                            {
                                'homeAway': 'away',
                                'score': '115',
                                'team': {'displayName': 'Denver Nuggets', 'location': 'Denver', 'name': 'Nuggets'},
                            },
                        ],
                    }
                ]
            },
            'boxscore': {
                'players': [
                    {
                        'statistics': [
                            {
                                'labels': ['PTS', 'REB', 'AST', '3PT'],
                                'athletes': [
                                    {'athlete': {'id': '15', 'displayName': 'Nikola Jokic'}, 'stats': ['30', '13', '8', '1-3']},
                                    {'athlete': {'id': '27', 'displayName': 'Jamal Murray'}, 'stats': ['20', '4', '6', '4-9']},
                                    {'athlete': {'id': '30', 'displayName': 'Draymond Green'}, 'stats': ['9', '7', '5', '1-4']},
                                    {'athlete': {'id': '31', 'displayName': 'Al Horford'}, 'stats': ['12', '5', '3', '2-5']},
                                    {'athlete': {'id': '32', 'displayName': 'Gui Santos'}, 'stats': ['20', '6', '2', '3-7']},
                                ],
                            }
                        ]
                    }
                ]
            },
        }


def test_moneyline_settles_using_team_location_aliases() -> None:
    provider = StubProvider()
    result = provider.get_team_result('Denver', event_id='evt-1')
    assert result is not None
    assert result.moneyline_win is True


def test_player_stats_settle_for_shorthand_name_and_threes_string_stats() -> None:
    provider = StubProvider()
    event = provider.resolve_player_event('Jokic', as_of=datetime.now(timezone.utc))
    assert event is not None
    assert provider.get_player_result('Jokic', 'player_points', event_id='evt-1') == 30.0
    assert provider.get_player_result('Murray', 'player_threes', event_id='evt-1') == 4.0



def test_player_stats_settle_for_first_name_and_partial_full_name_matches() -> None:
    provider = StubProvider()
    assert provider.resolve_player_event('Draymond', as_of=datetime.now(timezone.utc)) is not None
    assert provider.resolve_player_event('Horford', as_of=datetime.now(timezone.utc)) is not None
    assert provider.get_player_result('Draymond', 'player_assists', event_id='evt-1') == 5.0
    assert provider.get_player_result('Horford', 'player_rebounds', event_id='evt-1') == 5.0
    assert provider.get_player_result('Gui Santos', 'player_points', event_id='evt-1') == 20.0
