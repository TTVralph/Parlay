from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


class ESPNGamecastProvider:
    """Auxiliary ESPN live-event context provider for a single NBA event."""

    def __init__(self, timeout_s: float = 3.0) -> None:
        self._timeout_s = timeout_s
        self._cache: dict[str, dict[str, Any]] = {}

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

    def fetch_raw(self, event_id: str) -> dict[str, Any] | None:
        if event_id in self._cache:
            return self._cache[event_id]

        payload = self._fetch_json(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary',
            params={'event': event_id},
        )
        if payload is not None:
            self._cache[event_id] = payload
        return payload

    def fetch_normalized(self, event_id: str) -> dict[str, Any] | None:
        payload = self.fetch_raw(event_id)
        if not payload:
            return None

        header_competitions = ((payload.get('header') or {}).get('competitions') or [])
        competition = header_competitions[0] if header_competitions else {}
        status_type = ((competition.get('status') or {}).get('type') or {})
        status = {
            'state': str(status_type.get('state') or '').lower() or None,
            'description': str(status_type.get('description') or '').strip() or None,
            'detail': str(status_type.get('detail') or '').strip() or None,
            'is_final': bool(status_type.get('completed')),
        }

        situation = payload.get('situation') or {}
        return {
            'event_id': str(payload.get('id') or event_id),
            'status': status,
            'competitions': header_competitions,
            'clock': payload.get('clock') or competition.get('status', {}).get('displayClock'),
            'period': payload.get('quarter') or ((competition.get('status') or {}).get('period')),
            'situation': {
                'down_distance_text': situation.get('downDistanceText'),
                'last_play': situation.get('lastPlay') or {},
                'possession': ((situation.get('possession') or {}).get('displayName') if isinstance(situation.get('possession'), dict) else situation.get('possession')),
            },
            'leaders': payload.get('leaders') or [],
            'odds': payload.get('odds') or [],
            'injuries': payload.get('injuries') or [],
            'raw': payload,
        }
