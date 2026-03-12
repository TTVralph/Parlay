from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from app.models import Leg

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = 'https://api.betstack.com/v1'
_SUPPORTED_MARKETS = {
    'moneyline',
    'spread',
    'game_total',
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_threes',
    'player_pr',
    'player_pa',
    'player_ra',
    'player_pra',
}

_MARKET_ALIASES = {
    'h2h': 'moneyline',
    'moneyline': 'moneyline',
    'ml': 'moneyline',
    'spreads': 'spread',
    'spread': 'spread',
    'totals': 'game_total',
    'total': 'game_total',
    'game_total': 'game_total',
    'points': 'player_points',
    'player_points': 'player_points',
    'rebounds': 'player_rebounds',
    'player_rebounds': 'player_rebounds',
    'assists': 'player_assists',
    'player_assists': 'player_assists',
    'threes': 'player_threes',
    '3pm': 'player_threes',
    'player_threes': 'player_threes',
    'pr': 'player_pr',
    'pa': 'player_pa',
    'ra': 'player_ra',
    'pra': 'player_pra',
    'player_pr': 'player_pr',
    'player_pa': 'player_pa',
    'player_ra': 'player_ra',
    'player_pra': 'player_pra',
}


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r'-?\d+(?:\.\d+)?', value)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _normalize_market(raw: Any) -> str | None:
    if not raw:
        return None
    cleaned = str(raw).strip().lower().replace(' ', '_')
    return _MARKET_ALIASES.get(cleaned)


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('data', 'odds', 'markets', 'lines', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token for token in re.split(r'[^a-z0-9]+', value.lower()) if token}


def _looks_like_match(haystack: str | None, needle: str | None) -> bool:
    if not haystack or not needle:
        return False
    h = _tokenize(haystack)
    n = _tokenize(needle)
    if not h or not n:
        return False
    return len(h & n) >= max(1, min(2, len(n)))


class BetStackProvider:
    def __init__(self, api_key: str | None = None, *, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 8.0) -> None:
        self._api_key = (api_key or '').strip()
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout_seconds

    @classmethod
    def from_env(cls) -> 'BetStackProvider':
        return cls(api_key=os.getenv('BETSTACK_API_KEY', ''))

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def fetch_event_odds(self, *, sport: str = 'basketball', event_id: str | None = None, event_label: str | None = None, team: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        payload = self._request_json('/odds/consensus', params={'sport': sport, 'event_id': event_id})
        rows = [self._normalize_event_market_row(row) for row in _extract_rows(payload)]
        normalized = [row for row in rows if row]
        return [
            row
            for row in normalized
            if (not event_id or row.get('event_id') == event_id)
            and (not event_label or _looks_like_match(row.get('event_label'), event_label))
            and (not team or _looks_like_match(row.get('team'), team) or _looks_like_match(row.get('opponent'), team))
        ]

    def fetch_player_prop_lines(self, *, sport: str = 'basketball', player_name: str, event_id: str | None = None, event_label: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled or not player_name:
            return []
        payload = self._request_json('/odds/player-props/consensus', params={'sport': sport, 'event_id': event_id, 'player': player_name})
        rows = [self._normalize_player_prop_row(row) for row in _extract_rows(payload)]
        normalized = [row for row in rows if row]
        return [
            row
            for row in normalized
            if _looks_like_match(row.get('player'), player_name)
            and (not event_id or row.get('event_id') == event_id)
            and (not event_label or _looks_like_match(row.get('event_label'), event_label))
        ]

    def lookup_leg_line(self, leg: Leg) -> dict[str, Any] | None:
        if not self.enabled or leg.market_type not in _SUPPORTED_MARKETS:
            return None

        if leg.market_type.startswith('player_') and leg.player:
            rows = self.fetch_player_prop_lines(
                sport='basketball',
                player_name=leg.player,
                event_id=leg.event_id or leg.matched_event_id or leg.selected_event_id,
                event_label=leg.event_label or leg.matched_event_label or leg.selected_event_label,
            )
        else:
            rows = self.fetch_event_odds(
                sport='basketball',
                event_id=leg.event_id or leg.matched_event_id or leg.selected_event_id,
                event_label=leg.event_label or leg.matched_event_label or leg.selected_event_label,
                team=leg.team,
            )

        candidates = [row for row in rows if row.get('market_type') == leg.market_type]
        if not candidates:
            return None

        if leg.market_type == 'moneyline' and leg.team:
            team_specific = [row for row in candidates if _looks_like_match(row.get('team'), leg.team)]
            if team_specific:
                return team_specific[0]

        if leg.market_type != 'moneyline' and leg.direction:
            by_direction = [row for row in candidates if str(row.get('direction') or '').lower() == leg.direction]
            if by_direction:
                return by_direction[0]

        return candidates[0]

    def _request_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f'{self._base_url}{path}'
        headers = {'Authorization': f'Bearer {self._api_key}'}
        filtered_params = {k: v for k, v in params.items() if v not in (None, '')}
        try:
            response = httpx.get(url, headers=headers, params=filtered_params, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.info('BetStack request failed path=%s params=%s error=%s', path, filtered_params, exc)
            return {}

    def _normalize_event_market_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        market_type = _normalize_market(row.get('market') or row.get('market_type') or row.get('type'))
        if market_type not in {'moneyline', 'spread', 'game_total'}:
            return None
        line = _to_float(row.get('line') or row.get('point') or row.get('total') or row.get('handicap'))
        american_odds = _to_float(row.get('american_odds') or row.get('odds') or row.get('price'))
        return {
            'provider': 'betstack_consensus',
            'market_type': market_type,
            'event_id': row.get('event_id') or row.get('game_id'),
            'event_label': row.get('event') or row.get('event_label') or row.get('matchup'),
            'team': row.get('team') or row.get('home_team') or row.get('selection'),
            'opponent': row.get('opponent') or row.get('away_team'),
            'direction': str(row.get('direction') or '').lower() or None,
            'line': line,
            'american_odds': american_odds,
        }

    def _normalize_player_prop_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        market_type = _normalize_market(row.get('market') or row.get('market_type') or row.get('stat'))
        if market_type not in _SUPPORTED_MARKETS or market_type in {'moneyline', 'spread', 'game_total'}:
            return None
        return {
            'provider': 'betstack_consensus',
            'market_type': market_type,
            'event_id': row.get('event_id') or row.get('game_id'),
            'event_label': row.get('event') or row.get('event_label') or row.get('matchup'),
            'player': row.get('player') or row.get('player_name') or row.get('athlete'),
            'direction': str(row.get('direction') or row.get('side') or '').lower() or None,
            'line': _to_float(row.get('line') or row.get('point') or row.get('value')),
            'american_odds': _to_float(row.get('american_odds') or row.get('odds') or row.get('price')),
        }
