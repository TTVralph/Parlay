from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.services.request_cache import RequestCache


class ESPNScoreboardProvider:
    """Fetches ESPN NBA scoreboard slates and normalizes event metadata."""

    def __init__(self, timeout_s: float = 3.0, *, cache: RequestCache[str, dict[str, Any]] | None = None) -> None:
        self._timeout_s = timeout_s
        self._cache = cache or RequestCache[str, dict[str, Any]](max_entries=32)

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

    @staticmethod
    def _date_key(date_str: str) -> str:
        cleaned = date_str.strip()
        if re.fullmatch(r'\d{8}', cleaned):
            return cleaned
        parsed = datetime.fromisoformat(cleaned)
        return parsed.strftime('%Y%m%d')

    @staticmethod
    def _normalize_team(competitor: dict[str, Any]) -> dict[str, str | None]:
        team = competitor.get('team') or {}
        return {
            'name': str(team.get('displayName') or team.get('name') or '').strip() or None,
            'abbr': str(team.get('abbreviation') or '').strip() or None,
            'short_name': str(team.get('shortDisplayName') or '').strip() or None,
            'home_away': str(competitor.get('homeAway') or '').strip() or None,
        }

    @staticmethod
    def _status_fields(status_block: dict[str, Any]) -> tuple[str, bool, bool, bool]:
        status_type = (status_block.get('type') or {}) if isinstance(status_block, dict) else {}
        state = str(status_type.get('state') or '').lower() or 'scheduled'
        is_final = bool(status_type.get('completed')) or state == 'post'
        is_live = state in {'in', 'in_progress'}
        is_scheduled = not is_final and not is_live
        return state, is_final, is_live, is_scheduled

    def fetch_raw(self, date_str: str) -> dict[str, Any] | None:
        try:
            day_key = self._date_key(date_str)
        except ValueError:
            return None

        cached = self._cache.get(day_key)
        if cached is not None:
            return cached

        payload = self._fetch_json(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
            params={'dates': day_key},
        )
        if payload is not None:
            self._cache.set(day_key, payload)
        return payload

    def normalize_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        competitions = raw_event.get('competitions') or []
        if not competitions:
            return None
        competition = competitions[0]
        competitors = competition.get('competitors') or []
        home_raw = next((row for row in competitors if row.get('homeAway') == 'home'), None)
        away_raw = next((row for row in competitors if row.get('homeAway') == 'away'), None)
        if not home_raw or not away_raw:
            return None

        home = self._normalize_team(home_raw)
        away = self._normalize_team(away_raw)
        status_state, is_final, is_live, is_scheduled = self._status_fields(competition.get('status') or {})

        event_id = str(raw_event.get('id') or '').strip()
        start_time = str(competition.get('date') or raw_event.get('date') or '').strip() or None
        short_name = str(raw_event.get('shortName') or competition.get('shortName') or '').strip() or None

        if not event_id:
            return None

        return {
            'event_id': event_id,
            'date': start_time,
            'short_name': short_name,
            'home_team': home['name'],
            'away_team': away['name'],
            'home_team_abbr': home['abbr'],
            'away_team_abbr': away['abbr'],
            'competitors': [home, away],
            'status': status_state,
            'is_final': is_final,
            'is_live': is_live,
            'is_scheduled': is_scheduled,
        }

    def fetch_events_for_date(self, date_str: str) -> list[dict[str, Any]]:
        payload = self.fetch_raw(date_str)
        if not payload:
            return []
        events: list[dict[str, Any]] = []
        for raw_event in payload.get('events') or []:
            normalized = self.normalize_event(raw_event)
            if normalized is not None:
                events.append(normalized)
        return events

    @staticmethod
    def _norm(text: str | None) -> str:
        return re.sub(r'[^a-z0-9]', '', (text or '').lower())

    def resolve_event_candidates(self, date_str: str, *, team_query: str | None = None, opponent_query: str | None = None) -> list[dict[str, Any]]:
        events = self.fetch_events_for_date(date_str)
        if not events:
            return []

        team_norm = self._norm(team_query)
        opp_norm = self._norm(opponent_query)
        if not team_norm and not opp_norm:
            return events

        matches: list[dict[str, Any]] = []
        for event in events:
            teams = [
                str(event.get('home_team') or ''),
                str(event.get('away_team') or ''),
                str(event.get('home_team_abbr') or ''),
                str(event.get('away_team_abbr') or ''),
            ]
            norms = [self._norm(team) for team in teams if team]
            team_ok = not team_norm or any(team_norm == item or team_norm in item or item in team_norm for item in norms)
            opp_ok = not opp_norm or any(opp_norm == item or opp_norm in item or item in opp_norm for item in norms)
            if team_ok and opp_ok:
                matches.append(event)
        return matches
