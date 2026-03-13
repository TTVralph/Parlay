from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.services.play_by_play_provider import PlayByPlayEvent
from app.services.request_cache import RequestCache


@dataclass
class ESPNPlayFeedResult:
    source: str
    plays: list[PlayByPlayEvent]
    raw_payload: dict[str, Any] | None = None
    summary_payload: dict[str, Any] | None = None
    event_status: str | None = None


@dataclass
class _CacheEntry:
    value: dict[str, Any]
    fetched_at: datetime
    ttl_seconds: int

    def is_fresh(self, now: datetime) -> bool:
        return (now - self.fetched_at).total_seconds() <= self.ttl_seconds


class ESPNPlaysProvider:
    """Experimental ESPN plays provider with core->CDN fallback."""

    def __init__(self, timeout_s: float = 3.0, *, cache: RequestCache[str, Any] | None = None) -> None:
        self._timeout_s = timeout_s
        self._cache = cache or RequestCache[str, Any](max_entries=256)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _event_status(summary_payload: dict[str, Any] | None) -> str | None:
        if not isinstance(summary_payload, dict):
            return None
        competitions = ((summary_payload.get('header') or {}).get('competitions') or [])
        if not competitions:
            return None
        status_obj = ((competitions[0].get('status') or {}).get('type') or {})
        if status_obj.get('completed') is True:
            return 'final'
        state = str(status_obj.get('state') or '').strip().lower()
        if state in {'in', 'in_progress', 'inprogress', 'halftime'}:
            return 'live'
        if state:
            return state
        return None

    @staticmethod
    def _event_start(summary_payload: dict[str, Any] | None) -> datetime | None:
        if not isinstance(summary_payload, dict):
            return None
        competitions = ((summary_payload.get('header') or {}).get('competitions') or [])
        if not competitions:
            return None
        date_raw = str(competitions[0].get('date') or '').strip()
        if not date_raw:
            return None
        try:
            return datetime.fromisoformat(date_raw.replace('Z', '+00:00')).astimezone(timezone.utc)
        except ValueError:
            return None

    def _ttl_for_event(self, summary_payload: dict[str, Any] | None) -> int:
        now = self._now()
        status = self._event_status(summary_payload)
        if status == 'live':
            return 30
        if status == 'final':
            event_start = self._event_start(summary_payload)
            if event_start is not None and now - event_start <= timedelta(hours=24):
                return 600
            return 86400
        return 30

    def _event_cache_key(self, *, sport: str, event_id: str, feed_type: str) -> str:
        return f'normalized:{sport}:{event_id}:{feed_type}'

    def _fetch_event_feed_json(
        self,
        *,
        cache_key: str,
        url: str,
        params: dict[str, Any] | None = None,
        ttl_seconds: int,
    ) -> dict[str, Any] | None:
        now = self._now()
        cached = self._cache.get(cache_key)
        stale_value: dict[str, Any] | None = None
        if isinstance(cached, _CacheEntry):
            stale_value = cached.value
            if cached.is_fresh(now):
                return cached.value
        
        full_url = url
        if params:
            full_url = f'{url}?{urlencode(params)}'
        try:
            with urlopen(full_url, timeout=self._timeout_s) as resp:  # noqa: S310
                if getattr(resp, 'status', 200) != 200:
                    return stale_value
                payload = json.loads(resp.read().decode('utf-8'))
                if isinstance(payload, dict):
                    self._cache.set(cache_key, _CacheEntry(value=payload, fetched_at=now, ttl_seconds=ttl_seconds))
                    return payload
                return stale_value
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return stale_value
        except Exception:
            return stale_value

    def fetch_summary(self, event_id: str, sport: str = 'basketball', league: str = 'nba') -> dict[str, Any] | None:
        cache_key = self._event_cache_key(sport=sport, event_id=event_id, feed_type='summary')
        return self._fetch_event_feed_json(
            cache_key=cache_key,
            url=f'https://site.api.espn.com/apis/site/v2/sports/{sport}/leagues/{league}/summary',
            params={'event': event_id},
            ttl_seconds=30,
        )

    def fetch_core_plays(self, event_id: str, sport: str = 'basketball', league: str = 'nba', limit: int = 500) -> dict[str, Any] | None:
        summary_payload = self.fetch_summary(event_id, sport=sport, league=league)
        ttl_seconds = self._ttl_for_event(summary_payload)
        return self._fetch_event_feed_json(
            cache_key=self._event_cache_key(sport=sport, event_id=event_id, feed_type='core_plays'),
            url=f'https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{event_id}/competitions/{event_id}/plays',
            params={'limit': limit},
            ttl_seconds=ttl_seconds,
        )

    def fetch_cdn_playbyplay(self, event_id: str, sport: str = 'basketball', league: str = 'nba') -> dict[str, Any] | None:
        summary_payload = self.fetch_summary(event_id, sport=sport, league=league)
        ttl_seconds = self._ttl_for_event(summary_payload)
        return self._fetch_event_feed_json(
            cache_key=self._event_cache_key(sport=sport, event_id=event_id, feed_type='cdn_playbyplay'),
            url=f'https://cdn.espn.com/core/{league}/playbyplay',
            params={'xhr': 1, 'gameId': event_id},
            ttl_seconds=ttl_seconds,
        )

    @staticmethod
    def _extract_text_player(description: str, marker: str) -> str | None:
        match = re.search(rf"{marker}\s+([A-Za-z .\-'’]+)", description, re.I)
        if not match:
            return None
        return match.group(1).strip(' .')

    @staticmethod
    def _clock(play: dict[str, Any]) -> str | None:
        clock = play.get('clock')
        if isinstance(clock, dict):
            for key in ('displayValue', 'value'):
                value = str(clock.get(key) or '').strip()
                if value:
                    return value
        value = str(play.get('displayClock') or '').strip()
        return value or None

    @staticmethod
    def _period(play: dict[str, Any]) -> int | None:
        period = play.get('period')
        if isinstance(period, dict):
            number = period.get('number')
            if str(number or '').isdigit():
                return int(number)
        if str(period or '').isdigit():
            return int(period)
        for field in ('periodNumber',):
            value = play.get(field)
            if str(value or '').isdigit():
                return int(value)
        return None

    def _normalize_single_play(self, play: dict[str, Any], order: int) -> PlayByPlayEvent:
        description = str(play.get('text') or play.get('description') or '').strip()
        athletes = play.get('athletesInvolved') or []
        team_obj = play.get('team') or play.get('possession') or {}
        team = str(team_obj.get('displayName') or team_obj.get('name') or '').strip() or None

        primary_player = None
        if athletes:
            primary_player = str((athletes[0].get('athlete') or {}).get('displayName') or athletes[0].get('displayName') or '').strip() or None

        lower = description.lower()
        is_made_shot = (' makes ' in lower or ' made ' in lower) and 'free throw' not in lower
        is_three = is_made_shot and ('3-pt' in lower or '3pt' in lower or 'three point' in lower)
        is_rebound = 'rebound' in lower
        assist_player = self._extract_text_player(description, 'assist by')
        steal_player = self._extract_text_player(description, 'steal by')
        block_player = self._extract_text_player(description, 'block by')

        if not assist_player and len(athletes) > 1 and 'assist' in lower:
            assist_player = str((athletes[1].get('athlete') or {}).get('displayName') or athletes[1].get('displayName') or '').strip() or None

        raw_scoring = play.get('scoringPlay')
        is_scoring_play = bool(raw_scoring) if raw_scoring is not None else is_made_shot

        raw_type = play.get('type')
        if isinstance(raw_type, dict):
            event_type = str(raw_type.get('text') or raw_type.get('id') or 'unknown').lower()
        else:
            event_type = str(raw_type or 'unknown').lower()
        play_id = str(play.get('id') or play.get('playId') or '').strip() or None
        if play_id and description:
            event_type = f'{event_type}:{play_id}'

        return PlayByPlayEvent(
            event_order=order,
            event_type=event_type,
            description=description,
            period=self._period(play),
            clock=self._clock(play),
            team=team,
            primary_player=primary_player,
            assist_player=assist_player,
            steal_player=steal_player,
            block_player=block_player,
            is_scoring_play=is_scoring_play,
            is_made_shot=is_made_shot,
            is_three_pointer_made=is_three,
            is_rebound=is_rebound,
            is_assist=assist_player is not None,
            is_steal=steal_player is not None,
            is_block=block_player is not None,
        )

    def _normalize_core_payload(self, payload: dict[str, Any]) -> list[PlayByPlayEvent]:
        items = payload.get('items') or payload.get('plays') or []
        if not isinstance(items, list):
            return []
        return [self._normalize_single_play(play, index) for index, play in enumerate(items) if isinstance(play, dict)]

    def _normalize_cdn_payload(self, payload: dict[str, Any]) -> list[PlayByPlayEvent]:
        plays = payload.get('plays')
        if not isinstance(plays, list):
            plays = ((payload.get('gamepackageJSON') or {}).get('plays') or [])
        if not isinstance(plays, list):
            return []
        return [self._normalize_single_play(play, index) for index, play in enumerate(plays) if isinstance(play, dict)]

    def get_best_play_feed(
        self,
        event_id: str,
        *,
        sport: str = 'basketball',
        league: str = 'nba',
        limit: int = 500,
    ) -> ESPNPlayFeedResult | None:
        summary_payload = self.fetch_summary(event_id, sport=sport, league=league)
        cache_key = self._event_cache_key(sport=sport, event_id=event_id, feed_type='best_play_feed')
        cached = self._cache.get(cache_key)
        if isinstance(cached, ESPNPlayFeedResult):
            return cached

        core_payload = self.fetch_core_plays(event_id, sport=sport, league=league, limit=limit)
        core_normalized = self._normalize_core_payload(core_payload or {}) if core_payload else []
        if core_normalized:
            result = ESPNPlayFeedResult(
                source='espn_core_plays',
                plays=core_normalized,
                raw_payload=core_payload,
                summary_payload=summary_payload,
                event_status=self._event_status(summary_payload),
            )
            self._cache.set(cache_key, result)
            return result

        cdn_payload = self.fetch_cdn_playbyplay(event_id, sport=sport, league=league)
        cdn_normalized = self._normalize_cdn_payload(cdn_payload or {}) if cdn_payload else []
        if cdn_normalized:
            result = ESPNPlayFeedResult(
                source='espn_cdn_playbyplay',
                plays=cdn_normalized,
                raw_payload=cdn_payload,
                summary_payload=summary_payload,
                event_status=self._event_status(summary_payload),
            )
            self._cache.set(cache_key, result)
            return result

        return None
