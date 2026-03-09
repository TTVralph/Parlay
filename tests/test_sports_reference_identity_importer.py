from __future__ import annotations

from datetime import datetime

from app.identity_resolution import resolve_player_identity
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events
from app.sports_reference_identity import build_alias_keys, normalize_name, refresh_nba_identity_from_basketball_reference


class _Provider:
    def __init__(self) -> None:
        self.event = EventInfo(
            event_id='nba-evt-den-test',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Miami Heat',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )

    def resolve_team_event(self, team, as_of, *, include_historical=False):
        return None

    def resolve_player_event(self, player, as_of, *, include_historical=False):
        return None

    def resolve_team_event_candidates(self, team, as_of, *, include_historical=False):
        return [self.event] if team == 'Denver Nuggets' else []

    def resolve_player_event_candidates(self, player, as_of, *, include_historical=False):
        return [self.event]

    def get_team_result(self, team, event_id=None):
        return None

    def get_player_result(self, player, market_type, event_id=None):
        return None


def _teams_payload(team_ids: list[str]) -> dict[str, object]:
    return {
        'sports': [{'leagues': [{'teams': [{'team': {'id': tid, 'displayName': f'Team {tid}', 'abbreviation': f'T{tid}'}} for tid in team_ids]}]}]
    }


def _roster_payload(team_id: str, count: int) -> dict[str, object]:
    return {
        'athletes': [
            {
                'items': [
                    {'id': f'{team_id}{i}', 'fullName': f'Team {team_id} Player {i}'}
                    for i in range(1, count + 1)
                ]
            }
        ]
    }


def _flat_roster_payload(team_id: str, count: int) -> dict[str, object]:
    return {
        'athletes': [
            {'id': f'{team_id}{i}', 'displayName': f'Team {team_id} Flat Player {i}'}
            for i in range(1, count + 1)
        ]
    }


def test_alias_key_generation_handles_suffixes_accents_and_apostrophes() -> None:
    keys = build_alias_keys("Nikola Topić")
    assert 'nikola topic' in keys
    assert 'topic' in keys


def test_refresh_processes_all_teams_and_writes_espn_sourced_rows(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    team_ids = [str(i) for i in range(1, 31)]

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(team_ids)
        for tid in team_ids:
            if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id=tid):
                return _roster_payload(tid, 8)
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is True
    players = __import__('json').loads((tmp_path / 'nba_players.json').read_text())
    assert len(players) == 240
    assert players[0]['source_site'] == 'espn'


def test_refresh_marks_incomplete_and_refuses_overwrite(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    original_players = [{'canonical_player_id': 'nba-espn-keep', 'full_name': 'Keep Me'}]
    (tmp_path / 'nba_players.json').write_text(__import__('json').dumps(original_players))

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(['1', '2'])
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='1'):
            return _roster_payload('1', 1)
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='2'):
            raise RuntimeError('failed')
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is False
    assert __import__('json').loads((tmp_path / 'nba_players.json').read_text()) == original_players


def test_refresh_supports_flat_athletes_roster_shape(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(['1'])
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='1'):
            return _flat_roster_payload('1', 3)
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is True
    assert result['validation_report']['players_from_roster_pages'] == 3





def test_is_json_api_url_filters_website_pages() -> None:
    from app import sports_reference_identity as mod

    assert mod.is_json_api_url('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/1/roster') is True
    assert mod.is_json_api_url('https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/1') is True
    assert mod.is_json_api_url('/apis/site/v2/sports/basketball/nba/teams/1/athletes') is True
    assert mod.is_json_api_url('https://www.espn.com/nba/team/roster/_/name/atl/atlanta-hawks') is False
    assert mod.is_json_api_url('https://espn.com/nba/team/roster/_/name/atl/atlanta-hawks') is False
    assert mod.is_json_api_url('/nba/team/roster/_/name/atl/atlanta-hawks') is False



def test_refresh_uses_team_enable_roster_payload(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    enable_url = mod.ESPN_TEAM_URL_WITH_ROSTER_TEMPLATE.format(team_id='1')

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(['1'])
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='1'):
            raise RuntimeError('roster endpoint unavailable')
        if url == enable_url:
            return _roster_payload('1', 2)
        if url == mod.ESPN_TEAM_URL_TEMPLATE.format(team_id='1'):
            raise RuntimeError('should not need plain team endpoint when enable=roster works')
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is True
    assert result['validation_report']['players_from_roster_pages'] == 2

def test_refresh_follows_team_and_athlete_reference_links(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    team_url = mod.ESPN_TEAM_URL_TEMPLATE.format(team_id='1')
    roster_ref = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/1/athletes'
    athlete_ref = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes/123'

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(['1'])
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='1'):
            raise RuntimeError('missing roster endpoint')
        if url == team_url:
            return {'team': {'id': '1'}, 'links': [{'rel': ['athletes'], 'href': roster_ref}]}
        if url == roster_ref:
            return {'athletes': [{'$ref': athlete_ref}]}
        if url == athlete_ref:
            return {'id': '123', 'displayName': 'Linked Athlete'}
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is True
    assert result['validation_report']['players_from_roster_pages'] == 1
    players = __import__('json').loads((tmp_path / 'nba_players.json').read_text())
    assert players[0]['full_name'] == 'Linked Athlete'




def test_refresh_skips_non_api_roster_links(monkeypatch, tmp_path, caplog) -> None:
    from app import sports_reference_identity as mod

    team_url = mod.ESPN_TEAM_URL_TEMPLATE.format(team_id='1')
    website_roster = 'https://www.espn.com/nba/team/roster/_/name/atl/atlanta-hawks'
    api_roster_ref = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/1/athletes'

    def _fake_fetch(url: str) -> dict[str, object]:
        if url == mod.ESPN_TEAMS_URL:
            return _teams_payload(['1'])
        if url == mod.ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id='1'):
            raise RuntimeError('missing roster endpoint')
        if url == team_url:
            return {'links': [{'rel': ['roster'], 'href': website_roster}, {'rel': ['athletes'], 'href': api_roster_ref}]}
        if url == api_roster_ref:
            return {'athletes': [{'items': [{'id': '11', 'fullName': 'API Player'}]}]}
        raise RuntimeError(url)

    monkeypatch.setattr(mod.SportsReferenceFetcher, 'fetch_json', lambda self, url, *, context, use_cache=True: _fake_fetch(url))
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    caplog.set_level('INFO')
    result = refresh_nba_identity_from_basketball_reference()

    assert result['healthy'] is True
    assert 'Skipping non-API roster link: https://www.espn.com/nba/team/roster/_/name/atl/atlanta-hawks' in caplog.text
    players = __import__('json').loads((tmp_path / 'nba_players.json').read_text())
    assert players[0]['full_name'] == 'API Player'

def test_resolution_exposes_identity_metadata() -> None:
    result = resolve_player_identity('Nikola Jokic', sport='NBA')
    assert result.identity_source
    assert result.identity_last_refreshed_at


def test_resolver_sets_identity_diagnostics_fields() -> None:
    leg = Leg(
        raw_text='Nikola Jokic over 24.5 points',
        sport='NBA',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.95,
    )
    resolved = resolve_leg_events([leg], _Provider(), posted_at=None)
    assert resolved[0].identity_source
    assert resolved[0].resolved_player_name == 'Nikola Jokic'
    assert resolved[0].resolved_team_hint == 'Denver Nuggets'


def test_alias_generation_covers_target_rookies_and_special_names() -> None:
    for name in ['Alex Sarr', 'Nikola Topić', "Kel'el Ware"]:
        keys = build_alias_keys(name)
        assert keys
        assert normalize_name(name) in keys
