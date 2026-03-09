from __future__ import annotations

from datetime import date, datetime
import io
import json

from app.identity_resolution import (
    _player_directory,
    get_sport_adapters,
    refresh_nba_player_directory,
    resolve_player_identity,
)
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def _fake_urlopen_factory(payloads: dict[str, dict]):
    def _fake_urlopen(url: str, timeout: int = 0):
        body = payloads.get(url)
        if body is None:
            raise RuntimeError(f'unexpected URL: {url}')
        return _FakeResponse(json.dumps(body).encode('utf-8'))

    return _fake_urlopen


def _player(person_id: str, name: str, status: str = 'active') -> dict:
    return {'personId': person_id, 'fullName': name, 'rosterStatus': status}


def test_refresh_builds_broad_directory_and_includes_roster_only_players(monkeypatch, tmp_path) -> None:
    from app import identity_resolution as mod

    league_teams = []
    for idx in range(1, 31):
        players = [_player(str(idx * 100 + j), f'Player {idx}-{j}') for j in range(1, 13)]
        if idx == 1:
            players.append(_player('999', 'Jaren Jackson Jr.'))
        league_teams.append({'teamId': str(idx), 'teamName': f'Team {idx}', 'teamTricode': f'T{idx}', 'players': players})

    payloads = {
        mod._NBA_LEAGUE_DIRECTORY_URL: {'leagueRoster': {'teams': league_teams}},
        mod._ESPN_TEAMS_URL: {
            'sports': [{'leagues': [{'teams': [{'team': {'id': str(i), 'displayName': f'Team {i}', 'abbreviation': f'T{i}'}} for i in range(1, 31)]}]}]
        },
    }
    for i in range(1, 31):
        roster_items = [{'id': f'e{i}{j}', 'fullName': f'Player {i}-{j}'} for j in range(1, 13)]
        if i == 2:
            roster_items.append({'id': 'espn-bench', 'fullName': 'Bench Guy'})
        payloads[mod._ESPN_TEAM_ROSTER_URL.format(team_id=str(i))] = {'athletes': [{'items': roster_items}]}

    monkeypatch.setattr(mod, '_NBA_DIRECTORY_PATH', tmp_path / 'nba_directory.json')
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, '_maybe_refresh_nba_directory', lambda: None)
    monkeypatch.setattr(mod, '_MIN_EXPECTED_NBA_PLAYERS', 1)
    _player_directory.cache_clear()

    assert refresh_nba_player_directory(urlopen=_fake_urlopen_factory(payloads))

    adapter = get_sport_adapters()['NBA']
    names = {p.full_name for p in adapter.load_players()}
    assert len(names) >= 360
    assert 'Bench Guy' in names
    assert 'Jaren Jackson Jr.' in names


def test_refresh_updates_traded_player_team(monkeypatch, tmp_path) -> None:
    from app import identity_resolution as mod

    def _payload(team_name: str) -> dict[str, dict]:
        return {
            mod._NBA_LEAGUE_DIRECTORY_URL: {'leagueRoster': {'teams': [{'teamId': '1', 'teamName': team_name, 'players': [_player('15', 'AJ Green')]}]}},
            mod._ESPN_TEAMS_URL: {'sports': [{'leagues': [{'teams': [{'team': {'id': '1', 'displayName': team_name}}]}]}]},
            mod._ESPN_TEAM_ROSTER_URL.format(team_id='1'): {'athletes': [{'items': [{'id': '15', 'fullName': 'AJ Green'}]}]},
        }

    monkeypatch.setattr(mod, '_NBA_DIRECTORY_PATH', tmp_path / 'nba_directory.json')
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, '_maybe_refresh_nba_directory', lambda: None)
    monkeypatch.setattr(mod, '_MIN_EXPECTED_NBA_PLAYERS', 1)

    assert refresh_nba_player_directory(urlopen=_fake_urlopen_factory(_payload('Milwaukee Bucks')))
    _player_directory.cache_clear()
    assert resolve_player_identity('AJ Green', sport='NBA').resolved_team == 'Milwaukee Bucks'

    assert refresh_nba_player_directory(urlopen=_fake_urlopen_factory(_payload('Phoenix Suns')))
    _player_directory.cache_clear()
    assert resolve_player_identity('AJ Green', sport='NBA').resolved_team == 'Phoenix Suns'


def test_validation_flags_incomplete_directory(monkeypatch, tmp_path) -> None:
    from app import identity_resolution as mod

    payloads = {
        mod._NBA_LEAGUE_DIRECTORY_URL: {'leagueRoster': {'teams': [{'teamId': '1', 'teamName': 'Team 1', 'players': [_player('1', 'Only Player')]}]}},
        mod._ESPN_TEAMS_URL: {'sports': [{'leagues': [{'teams': [{'team': {'id': '1', 'displayName': 'Team 1'}}]}]}]},
        mod._ESPN_TEAM_ROSTER_URL.format(team_id='1'): {'athletes': [{'items': [{'id': '1', 'fullName': 'Only Player'}]}]},
    }

    monkeypatch.setattr(mod, '_NBA_DIRECTORY_PATH', tmp_path / 'nba_directory.json')
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    assert refresh_nba_player_directory(urlopen=_fake_urlopen_factory(payloads))
    data = json.loads((tmp_path / 'nba_directory.json').read_text())
    assert data['validation_report']['severe_failure'] is True
    assert data['validation_report']['total_players_loaded'] == 1


class _HistoricalProvider:
    def __init__(self) -> None:
        self.old_event = EventInfo(
            event_id='nba-old',
            sport='NBA',
            home_team='Milwaukee Bucks',
            away_team='Boston Celtics',
            start_time=datetime.fromisoformat('2026-01-01T00:00:00+00:00'),
        )

    def resolve_team_event(self, team, as_of, *, include_historical=False):
        return None

    def resolve_player_event(self, player, as_of, *, include_historical=False):
        return None

    def resolve_player_event_candidates(self, player, as_of, *, include_historical=False):
        return [self.old_event]

    def resolve_team_event_candidates(self, team, as_of, *, include_historical=False):
        return [self.old_event] if team == 'Milwaukee Bucks' else []

    def resolve_player_team(self, player, as_of, *, include_historical=False):
        if include_historical and as_of and as_of.date() <= date.fromisoformat('2026-01-01'):
            return 'Milwaukee Bucks'
        return 'Phoenix Suns'

    def get_team_result(self, team, event_id=None):
        return None

    def get_player_result(self, player, market_type, event_id=None):
        return None


def test_historical_matching_uses_event_context_over_current_team() -> None:
    leg = Leg(
        raw_text='AJ Green over 1.5 threes',
        sport='NBA',
        market_type='player_threes',
        player='AJ Green',
        direction='over',
        line=1.5,
        confidence=0.9,
    )
    resolved = resolve_leg_events([leg], _HistoricalProvider(), posted_at=date.fromisoformat('2026-01-01'), include_historical=True)
    assert resolved[0].event_id == 'nba-old'
