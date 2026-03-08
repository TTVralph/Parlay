from __future__ import annotations

from datetime import date
import logging
import os
from typing import Any

import httpx


_BASE_URL = 'https://allsportsapi2.p.rapidapi.com'
_RAPIDAPI_HOST = 'allsportsapi2.p.rapidapi.com'
logger = logging.getLogger(__name__)


class AllSportsError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AllSportsClient:
    def __init__(self, api_key: str, base_url: str = _BASE_URL, timeout_seconds: float = 15.0) -> None:
        if not api_key:
            raise AllSportsError('RAPIDAPI_KEY is not configured', status_code=500)
        self._base_url = base_url.rstrip('/')
        self._headers = {
            'x-rapidapi-host': _RAPIDAPI_HOST,
            'x-rapidapi-key': api_key,
        }
        self._timeout = timeout_seconds

    @classmethod
    def from_env(cls) -> 'AllSportsClient':
        return cls(api_key=os.getenv('RAPIDAPI_KEY', '').strip())

    def get_games_by_date(self, game_date: date) -> list[dict[str, Any]]:
        path = f'/api/basketball/matches/{game_date.day}/{game_date.month}/{game_date.year}'
        payload = self._request_json(path)
        events = payload.get('events') if isinstance(payload, dict) else None
        if isinstance(events, list):
            return events
        logger.info('AllSports games payload missing events list for %s', game_date.isoformat())
        return []

    def get_match_statistics(self, match_id: str) -> Any:
        path = f'/api/basketball/match/{match_id}/statistics'
        return self._request_json(path)

    def _request_json(self, path: str) -> Any:
        url = f'{self._base_url}{path}'
        logger.debug('AllSports request path=%s', path)
        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout)
        except httpx.RequestError as exc:
            logger.exception('AllSports request failed path=%s error=%s', path, exc)
            raise AllSportsError('AllSports API request failed') from exc

        if response.status_code == 404:
            logger.info('AllSports resource missing path=%s status=404', path)
            raise AllSportsError('Match not found', status_code=404)
        if response.status_code >= 400:
            logger.warning('AllSports API failure path=%s status=%s body=%s', path, response.status_code, response.text[:400])
            raise AllSportsError(f'AllSports API error ({response.status_code})')

        try:
            return response.json()
        except ValueError as exc:
            logger.exception('AllSports returned invalid JSON path=%s', path)
            raise AllSportsError('AllSports API returned invalid JSON') from exc
