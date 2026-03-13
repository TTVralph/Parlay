from app.services.espn_plays_provider import ESPNPlaysProvider


class StubESPNPlaysProvider(ESPNPlaysProvider):
    def __init__(self, *, core_payload=None, cdn_payload=None):
        super().__init__()
        self._core_payload = core_payload
        self._cdn_payload = cdn_payload

    def fetch_core_plays(self, event_id: str, sport: str = 'basketball', league: str = 'nba', limit: int = 500):
        return self._core_payload

    def fetch_cdn_playbyplay(self, event_id: str, league: str = 'nba'):
        return self._cdn_payload


def test_core_plays_normalization_extracts_player_and_clues() -> None:
    provider = StubESPNPlaysProvider(
        core_payload={
            'items': [
                {
                    'id': '401',
                    'text': 'Nikola Jokic makes 3-pt jump shot (assist by Jamal Murray)',
                    'period': {'number': 4},
                    'clock': {'displayValue': '05:42'},
                    'team': {'displayName': 'Nuggets'},
                    'athletesInvolved': [
                        {'athlete': {'displayName': 'Nikola Jokic'}},
                        {'athlete': {'displayName': 'Jamal Murray'}},
                    ],
                    'scoringPlay': True,
                    'type': {'text': 'madeShot'},
                }
            ]
        }
    )

    result = provider.get_best_play_feed('evt-1')
    assert result is not None
    assert result.source == 'espn_core_plays'
    assert len(result.plays) == 1
    play = result.plays[0]
    assert play.primary_player == 'Nikola Jokic'
    assert play.assist_player == 'Jamal Murray'
    assert play.is_scoring_play is True
    assert play.is_three_pointer_made is True
    assert play.period == 4
    assert play.clock == '05:42'


def test_falls_back_to_cdn_when_core_unavailable() -> None:
    provider = StubESPNPlaysProvider(
        core_payload={'items': []},
        cdn_payload={
            'gamepackageJSON': {
                'plays': [
                    {
                        'id': '501',
                        'text': 'Jayson Tatum defensive rebound',
                        'period': {'number': 4},
                        'clock': {'displayValue': '00:41'},
                        'athletesInvolved': [{'athlete': {'displayName': 'Jayson Tatum'}}],
                        'team': {'displayName': 'Celtics'},
                        'type': 'rebound',
                    }
                ]
            }
        },
    )

    result = provider.get_best_play_feed('evt-2')
    assert result is not None
    assert result.source == 'espn_cdn_playbyplay'
    assert result.plays[0].is_rebound is True
