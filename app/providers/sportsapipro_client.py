from __future__ import annotations

import logging
import os
from typing import Any

import httpx


_BASE_URL = 'https://v1.basketball.sportsapipro.com'
logger = logging.getLogger(__name__)


class SportsAPIProError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        code: str = 'sportsapipro_error',
        details: dict[str, Any] | None = None,
    ) -> None:
    def __init__(self, message: str, status_code: int = 502, code: str = 'upstream_error') -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class SportsAPIProClient:
    def __init__(self, api_key: str, base_url: str = _BASE_URL, timeout_seconds: float = 15.0) -> None:
        if not api_key:
            raise SportsAPIProError(
                'SPORTSAPIPRO_KEY is not configured',
                status_code=500,
                code='sportsapipro_missing_key',
            )
            raise SportsAPIProError('SPORTSAPIPRO_KEY is not configured', status_code=500, code='missing_api_key')
        self._base_url = base_url.rstrip('/')
        self._headers = {'x-api-key': api_key}
        self._timeout = timeout_seconds

    @classmethod
    def from_env(cls) -> 'SportsAPIProClient':
        return cls(api_key=os.getenv('SPORTSAPIPRO_KEY', '').strip())

    def status(self) -> Any:
        return self._request_json('/status')

    def get_games_current(self) -> Any:
        return self._request_json('/games/current')

    def get_games_results(self, *, game_date: str | None = None) -> Any:
        params: dict[str, Any] = {}
        if game_date:
            params['date'] = game_date
        return self._request_json('/games/results', params=params or None)

    def get_game(self, game_id: str) -> Any:
        return self._request_json('/game', params={'id': game_id})

    def get_athlete_games(self, athlete_id: str) -> Any:
        return self._request_json('/athletes/games', params={'id': athlete_id})
    def get_current_games(self) -> Any:
        return self._request_json('/games/current')

    def get_game_results(self) -> Any:
        return self._request_json('/games/results')

    def get_game(self, game_id: str) -> Any:
        return self._request_json('/game', params={'gameId': game_id})

    def get_athlete_games(self, athlete_id: str) -> Any:
        return self._request_json('/athletes/games', params={'athleteId': athlete_id})

    def search(self, query: str) -> Any:
        return self._request_json('/search', params={'q': query})

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f'{self._base_url}{path}'
        logger.debug('SportsAPI Pro request path=%s params=%s', path, sorted((params or {}).keys()))
        try:
            response = httpx.get(url, headers=self._headers, params=params, timeout=self._timeout)
        except httpx.RequestError as exc:
            logger.exception('SportsAPI Pro request failed path=%s error=%s', path, exc)
            raise SportsAPIProError(
                'SportsAPI Pro request failed',
                code='sportsapipro_request_error',
                details={'path': path},
            ) from exc

        if response.status_code in (401, 403):
            logger.warning('SportsAPI Pro auth failure path=%s status=%s', path, response.status_code)
            raise SportsAPIProError(
                'SportsAPI Pro authentication failed',
                status_code=502,
                code='sportsapipro_auth_error',
                details={'path': path, 'upstream_status': response.status_code},
            )
        if response.status_code == 404:
            raise SportsAPIProError(
                'SportsAPI Pro resource not found',
                status_code=404,
                code='sportsapipro_not_found',
                details={'path': path},
            )
        if response.status_code >= 400:
            logger.warning(
                'SportsAPI Pro upstream error path=%s status=%s body=%s',
                path,
                response.status_code,
                response.text[:400],
            )
            raise SportsAPIProError(
                f'SportsAPI Pro upstream error ({response.status_code})',
                status_code=502,
                code='sportsapipro_upstream_error',
                details={'path': path, 'upstream_status': response.status_code},
    def _request_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f'{self._base_url}{path}'
        logger.debug('SportsAPI Pro request path=%s params=%s', path, sorted((params or {}).keys()))
        try:
            response = httpx.get(url, params=params, headers=self._headers, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            logger.warning('SportsAPI Pro timeout path=%s params=%s', path, params)
            raise SportsAPIProError('SportsAPI Pro request timed out', status_code=504, code='timeout') from exc
        except httpx.RequestError as exc:
            logger.exception('SportsAPI Pro network request failed path=%s params=%s', path, params)
            raise SportsAPIProError('SportsAPI Pro request failed', status_code=502, code='network_error') from exc

        if response.status_code in (401, 403):
            logger.warning('SportsAPI Pro auth failure path=%s status=%s', path, response.status_code)
            raise SportsAPIProError('SportsAPI Pro authentication failed', status_code=502, code='auth_error')
        if response.status_code == 404:
            logger.info('SportsAPI Pro resource missing path=%s params=%s', path, params)
            raise SportsAPIProError('SportsAPI Pro resource not found', status_code=404, code='not_found')
        if response.status_code >= 400:
            logger.warning(
                'SportsAPI Pro upstream error path=%s status=%s params=%s body=%s',
                path,
                response.status_code,
                params,
                response.text[:300],
            )
            raise SportsAPIProError(
                f'SportsAPI Pro API error ({response.status_code})',
                status_code=502,
                code='upstream_error',
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.exception('SportsAPI Pro returned invalid JSON path=%s', path)
            raise SportsAPIProError(
                'SportsAPI Pro returned invalid JSON',
                code='sportsapipro_invalid_json',
                details={'path': path},
            ) from exc
            raise SportsAPIProError('SportsAPI Pro API returned invalid JSON', status_code=502, code='invalid_json') from exc
