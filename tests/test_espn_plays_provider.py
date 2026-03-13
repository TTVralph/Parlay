from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.espn_plays_provider import ESPNPlaysProvider, _CacheEntry


class StubESPNPlaysProvider(ESPNPlaysProvider):
    def __init__(self, *, core_payload=None, cdn_payload=None, summary_payload=None):
        super().__init__()
        self._core_payload = core_payload
        self._cdn_payload = cdn_payload
        self._summary_payload = summary_payload

    def fetch_summary(self, event_id: str, sport: str = 'basketball', league: str = 'nba'):
        return self._summary_payload

    def fetch_core_plays(self, event_id: str, sport: str = 'basketball', league: str = 'nba', limit: int = 500):
        return self._core_payload

    def fetch_cdn_playbyplay(self, event_id: str, sport: str = 'basketball', league: str = 'nba'):
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


def test_ttl_selection_by_event_state() -> None:
    provider = ESPNPlaysProvider()
    live_summary = {'header': {'competitions': [{'status': {'type': {'state': 'in'}}}]}}
    recent_final = {
        'header': {
            'competitions': [
                {
                    'status': {'type': {'completed': True}},
                    'date': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                }
            ]
        }
    }
    old_final = {
        'header': {
            'competitions': [
                {
                    'status': {'type': {'completed': True}},
                    'date': (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                }
            ]
        }
    }
    assert provider._ttl_for_event(live_summary) == 30
    assert provider._ttl_for_event(recent_final) == 600
    assert provider._ttl_for_event(old_final) == 86400


def test_stale_cache_is_returned_when_refresh_fails() -> None:
    provider = ESPNPlaysProvider()
    key = 'normalized:basketball:evt-9:core_plays'
    provider._cache.set(
        key,
        _CacheEntry(value={'items': [{'id': '123', 'text': 'Old payload'}]}, fetched_at=datetime.now(timezone.utc) - timedelta(minutes=3), ttl_seconds=1),
    )

    payload = provider._fetch_event_feed_json(
        cache_key=key,
        url='http://localhost:9/unreachable',
        ttl_seconds=1,
    )
    assert payload == {'items': [{'id': '123', 'text': 'Old payload'}]}
