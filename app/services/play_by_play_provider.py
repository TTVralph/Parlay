from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.services.request_cache import RequestCache


@dataclass
class PlayByPlayEvent:
    event_order: int
    event_type: str
    description: str
    period: int | None
    clock: str | None
    team: str | None
    primary_player: str | None
    assist_player: str | None = None
    steal_player: str | None = None
    block_player: str | None = None
    is_scoring_play: bool = False
    is_made_shot: bool = False
    is_three_pointer_made: bool = False
    is_rebound: bool = False
    is_assist: bool = False
    is_steal: bool = False
    is_block: bool = False


class ESPNPlayByPlayProvider:
    def __init__(self, timeout_s: float = 3.0, *, cache: RequestCache[str, dict[str, Any]] | None = None) -> None:
        self._timeout_s = timeout_s
        self._cache = cache or RequestCache[str, dict[str, Any]](max_entries=128)

    def _fetch_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        full_url = url
        if params:
            full_url = f'{url}?{urlencode(params)}'
        try:
            with urlopen(full_url, timeout=self._timeout_s) as resp:  # noqa: S310
                if getattr(resp, 'status', 200) != 200:
                    return None
                return json.loads(resp.read().decode('utf-8'))
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
        except Exception:
            return None

    def _summary(self, event_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(event_id)
        if cached is not None:
            return cached

        payload = self._fetch_json(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary',
            params={'event': event_id},
        )
        if payload is not None:
            self._cache.set(event_id, payload)
        return payload

    @staticmethod
    def _extract_text_player(description: str, marker: str) -> str | None:
        match = re.search(rf"{marker}\s+([A-Za-z .\-'’]+)", description, re.I)
        if not match:
            return None
        return match.group(1).strip(' .')

    def get_normalized_events(self, event_id: str) -> list[PlayByPlayEvent] | None:
        summary = self._summary(event_id)
        if not summary:
            return None
        plays = summary.get('plays') or []
        if not plays:
            return None

        normalized: list[PlayByPlayEvent] = []
        for index, play in enumerate(plays):
            description = str(play.get('text') or '').strip()
            athletes = play.get('athletesInvolved') or []
            team = str((play.get('team') or {}).get('displayName') or '').strip() or None
            primary_player = None
            if athletes:
                primary_player = str((athletes[0].get('athlete') or {}).get('displayName') or '').strip() or None

            lower = description.lower()
            is_made_shot = ' makes ' in lower and ' free throw' not in lower
            is_three = is_made_shot and ('3-pt' in lower or '3pt' in lower or 'three point' in lower)
            assist_player = self._extract_text_player(description, 'assist by')
            steal_player = self._extract_text_player(description, 'steal by')
            block_player = self._extract_text_player(description, 'block by')
            is_rebound = 'rebound' in lower

            if not assist_player and len(athletes) > 1 and 'assist' in lower:
                assist_player = str((athletes[1].get('athlete') or {}).get('displayName') or '').strip() or None
            if not steal_player and len(athletes) > 1 and 'steal' in lower:
                steal_player = str((athletes[1].get('athlete') or {}).get('displayName') or '').strip() or None
            if not block_player and len(athletes) > 1 and 'block' in lower:
                block_player = str((athletes[1].get('athlete') or {}).get('displayName') or '').strip() or None

            normalized.append(
                PlayByPlayEvent(
                    event_order=index,
                    event_type=str(play.get('type') or '').lower() or 'unknown',
                    description=description,
                    period=int(play.get('period', {}).get('number')) if isinstance(play.get('period'), dict) and str(play.get('period', {}).get('number') or '').isdigit() else None,
                    clock=str((play.get('clock') or {}).get('displayValue') or '').strip() or None,
                    team=team,
                    primary_player=primary_player,
                    assist_player=assist_player,
                    steal_player=steal_player,
                    block_player=block_player,
                    is_scoring_play=bool(play.get('scoringPlay')),
                    is_made_shot=is_made_shot,
                    is_three_pointer_made=is_three,
                    is_rebound=is_rebound,
                    is_assist=assist_player is not None,
                    is_steal=steal_player is not None,
                    is_block=block_player is not None,
                )
            )
        return normalized
