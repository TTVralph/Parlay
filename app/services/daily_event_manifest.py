from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from app.models import Leg
from app.services.request_cache import RequestCache
from app.services.scoreboard_provider import ESPNScoreboardProvider


class DailyEventManifestService:
    """Builds and reuses normalized event indexes for a sport/date."""

    def __init__(
        self,
        *,
        scoreboard_provider: ESPNScoreboardProvider | None = None,
        cache: RequestCache[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self._scoreboard_provider = scoreboard_provider or ESPNScoreboardProvider()
        self._cache = cache or RequestCache[tuple[str, str], dict[str, Any]](max_entries=64)

    @staticmethod
    def _norm(value: str | None) -> str:
        return re.sub(r'[^a-z0-9]', '', (value or '').lower())

    @staticmethod
    def _date_key(value: str | date | datetime) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        cleaned = str(value).strip()
        if re.fullmatch(r'\d{8}', cleaned):
            return datetime.strptime(cleaned, '%Y%m%d').date().isoformat()  # noqa: DTZ007
        return datetime.fromisoformat(cleaned).date().isoformat()

    @staticmethod
    def _team_aliases(event: dict[str, Any]) -> list[str]:
        aliases: list[str] = []
        for key in ('home_team', 'away_team', 'home_team_abbr', 'away_team_abbr'):
            value = str(event.get(key) or '').strip()
            if value and value not in aliases:
                aliases.append(value)
        for competitor in event.get('competitors') or []:
            if not isinstance(competitor, dict):
                continue
            for key in ('name', 'abbr', 'short_name'):
                value = str(competitor.get(key) or '').strip()
                if value and value not in aliases:
                    aliases.append(value)
        return aliases

    @staticmethod
    def _extract_player_pool(raw_event: dict[str, Any]) -> list[str]:
        competition = ((raw_event.get('competitions') or [{}])[0]) if raw_event else {}
        pool: list[str] = []
        for competitor in competition.get('competitors') or []:
            roster = competitor.get('roster') or competitor.get('athletes') or []
            for athlete in roster:
                athlete_obj = athlete.get('athlete') if isinstance(athlete, dict) else None
                source = athlete_obj if isinstance(athlete_obj, dict) else athlete
                if not isinstance(source, dict):
                    continue
                name = str(source.get('displayName') or source.get('fullName') or source.get('name') or '').strip()
                if name and name not in pool:
                    pool.append(name)
        return pool

    def build_daily_manifest(self, sport: str, date_value: str | date | datetime) -> dict[str, Any]:
        date_key = self._date_key(date_value)
        if sport != 'NBA':
            return {'sport': sport, 'date': date_key, 'events': []}

        payload = self._scoreboard_provider.fetch_raw(date_key)
        raw_events = (payload or {}).get('events') or []
        manifest_events: list[dict[str, Any]] = []

        for raw_event in raw_events:
            normalized = self._scoreboard_provider.normalize_event(raw_event)
            if not normalized:
                continue
            aliases = self._team_aliases(normalized)
            normalized_keys = sorted({self._norm(alias) for alias in aliases if self._norm(alias)})
            manifest_events.append(
                {
                    'event_id': normalized.get('event_id'),
                    'home_team': normalized.get('home_team'),
                    'away_team': normalized.get('away_team'),
                    'home_team_abbr': normalized.get('home_team_abbr'),
                    'away_team_abbr': normalized.get('away_team_abbr'),
                    'team_aliases': aliases,
                    'game_status': normalized.get('status'),
                    'start_time': normalized.get('date'),
                    'date': normalized.get('date'),
                    'short_name': normalized.get('short_name'),
                    'player_pool': self._extract_player_pool(raw_event),
                    'normalized_team_keys': normalized_keys,
                }
            )

        return {'sport': sport, 'date': date_key, 'events': manifest_events}

    def get_daily_manifest(self, sport: str, date_value: str | date | datetime) -> dict[str, Any] | None:
        try:
            date_key = self._date_key(date_value)
        except ValueError:
            return None

        cache_key = (sport, date_key)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        manifest = self.build_daily_manifest(sport, date_key)
        self._cache.set(cache_key, manifest)
        return manifest

    def find_candidate_events_for_leg(self, manifest: dict[str, Any] | None, leg: Leg) -> list[dict[str, Any]]:
        if not manifest:
            return []
        events = manifest.get('events') if isinstance(manifest, dict) else None
        if not isinstance(events, list):
            return []

        opponent = self._opponent_from_leg(leg)
        team_query = leg.resolved_team or leg.team
        team_norm = self._norm(team_query)
        opp_norm = self._norm(opponent)

        if not team_norm and not opp_norm:
            return [event for event in events if isinstance(event, dict)]

        matches: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            team_keys = [self._norm(value) for value in (event.get('normalized_team_keys') or [])]
            team_keys = [key for key in team_keys if key]
            team_ok = not team_norm or any(team_norm == key or team_norm in key or key in team_norm for key in team_keys)
            opp_ok = not opp_norm or any(opp_norm == key or opp_norm in key or key in opp_norm for key in team_keys)
            if team_ok and opp_ok:
                matches.append(event)
        return matches

    @staticmethod
    def _opponent_from_leg(leg: Leg) -> str | None:
        for note in leg.notes:
            if note.startswith('Opponent context: '):
                return note.split(':', 1)[1].strip() or None
        match = re.search(r'\sv(?:s|\.|ersus)\s+([a-z0-9 .\-]+)$', leg.raw_text, re.I)
        return match.group(1).strip() if match else None
