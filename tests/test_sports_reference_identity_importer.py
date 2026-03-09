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


INDEX_HTML = '''
<table>
<tr><th data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></th><td data-stat="year_max">2025</td></tr>
</table>
'''

TEAMS_HTML = '''
<a href="/teams/ATL/">Atlanta Hawks</a>
<a href="/teams/WAS/">Washington Wizards</a>
<a href="/teams/CHO/">Charlotte Hornets</a>
'''

PLAYER_HTML = '<div>Team:</strong> <a href="/teams/WAS/2026.html">Washington Wizards</a></div>'


def test_alias_key_generation_handles_suffixes_accents_and_apostrophes() -> None:
    keys = build_alias_keys("Nikola Topić")
    assert 'nikola topic' in keys
    assert 'topic' in keys
    keys = build_alias_keys("Kel'el Ware")
    assert 'kelel ware' in keys
    assert 'kel el ware' in keys
    assert 'ware' in keys
    keys = build_alias_keys('Michael Porter Jr.')
    assert 'michael porter jr' in keys
    assert 'michael porter' in keys


def test_refresh_processes_all_30_teams_and_merges_roster_only_players(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    fetched_rosters: list[str] = []

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return INDEX_HTML
        if '/players/' in url and any(url.endswith(f'/{ch}/') for ch in 'bcdefghijklnmopqrstuvwxyz'):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        for team_abbr in mod.NBA_TEAM_ABBREVIATIONS:
            roster_url = mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=datetime.now().year)
            if url == roster_url:
                fetched_rosters.append(team_abbr)
                rows = []
                for i in range(1, 9):
                    player_code = f'{team_abbr.lower()}rook{i:02d}'
                    player_name = f'{team_abbr} RosterOnly {i}'
                    rows.append(f'<tr><td data-stat="player"><a href="/players/{player_code[0]}/{player_code}.html">{player_name}</a></td></tr>')
                return '<table id="roster"><tbody>' + ''.join(rows) + '</tbody></table>'
        if '/players/' in url and url.endswith('.html'):
            return PLAYER_HTML
        raise RuntimeError(url)

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert set(fetched_rosters) == set(mod.NBA_TEAM_ABBREVIATIONS)
    assert result['validation_report']['healthy'] is True
    assert result['validation_report']['roster_only_players_added'] >= 30

    players = (tmp_path / 'nba_players.json').read_text()
    assert 'WAS RosterOnly 1' in players
    assert 'team_id' in players


def test_refresh_marks_incomplete_when_too_many_team_rosters_fail(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return INDEX_HTML
        if '/players/' in url and any(url.endswith(f'/{ch}/') for ch in 'bcdefghijklnmopqrstuvwxyz'):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        roster_ok = mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr='ATL', season_year=datetime.now().year)
        if url == roster_ok:
            return '<table id="roster"><tbody><tr><td data-stat="player"><a href="/players/a/atlplay01.html">ATL Player</a></td></tr></tbody></table>'
        if '/teams/' in url and url.endswith('.html'):
            raise RuntimeError('team roster failed')
        if '/players/' in url and url.endswith('.html'):
            return PLAYER_HTML
        raise RuntimeError(url)

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is False
    assert len(result['validation_report']['teams_failed']) == 29
    assert result['validation_report']['refresh_incomplete'] is True


def test_resolution_exposes_basketball_reference_metadata() -> None:
    result = resolve_player_identity('Nikola Jokic', sport='NBA')
    assert result.identity_source == 'basketball-reference'
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
    assert resolved[0].identity_source == 'basketball-reference'
    assert resolved[0].resolved_player_name == 'Nikola Jokic'
    assert resolved[0].resolved_team_hint == 'Denver Nuggets'


def test_alias_generation_covers_target_rookies_and_special_names() -> None:
    names = [
        'Jared McCain',
        'Zaccharie Risacher',
        'Alex Sarr',
        'Reed Sheppard',
        'Stephon Castle',
        'Matas Buzelis',
        'Ron Holland',
        'Donovan Clingan',
        'Rob Dillingham',
        'Nikola Topić',
        'Tidjane Salaun',
        'Yves Missi',
        'Tristan da Silva',
        'Jaylon Tyson',
        "Kel'el Ware",
    ]
    for name in names:
        keys = build_alias_keys(name)
        assert keys
        assert normalize_name(name) in keys


def test_refresh_preserves_roster_assignment_over_player_page_metadata(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return '<table><tr><th data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></th><td data-stat="year_max">2026</td></tr></table>'
        if '/players/' in url and url.endswith('/b/'):
            return '<table><tr><th data-stat="player"><a href="/players/b/benchman01.html">Bench Man</a></th><td data-stat="year_max">2026</td></tr></table>'
        if '/players/' in url and any(url.endswith(f'/{ch}/') for ch in 'cdefghijklnmopqrstuvwxyz'):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        for team_abbr in mod.NBA_TEAM_ABBREVIATIONS:
            roster_url = mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=datetime.now().year)
            if url == roster_url:
                return '<table id="roster"><tbody><tr><td data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></td></tr></tbody></table>'
        if '/players/' in url and url.endswith('.html'):
            return '<div>Team:</strong> <a href="/teams/ATL/2026.html">Atlanta Hawks</a></div>'
        raise RuntimeError(url)

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    refresh_nba_identity_from_basketball_reference()
    players = __import__('json').loads((tmp_path / 'nba_players.json').read_text())
    alex = next(p for p in players if p['canonical_player_id'] == 'nba-br-alexsar01')
    assert alex['current_team_abbr'] != 'ATL'
    assert alex['roster_data_applied'] is True


def test_unhealthy_refresh_with_null_team_fields_does_not_overwrite_cache(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    original_players = [{'canonical_player_id': 'nba-br-keepme01', 'full_name': 'Keep Me'}]
    (tmp_path / 'nba_players.json').write_text(__import__('json').dumps(original_players))

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return '<table><tr><th data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></th><td data-stat="year_max">2026</td></tr></table>'
        if '/players/' in url and url.endswith('/b/'):
            return '<table><tr><th data-stat="player"><a href="/players/b/benchman01.html">Bench Man</a></th><td data-stat="year_max">2026</td></tr></table>'
        if '/players/' in url and any(url.endswith(f'/{ch}/') for ch in 'cdefghijklnmopqrstuvwxyz'):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        for team_abbr in mod.NBA_TEAM_ABBREVIATIONS:
            roster_url = mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=datetime.now().year)
            if url == roster_url:
                return '<table id="roster"><tbody><tr><td data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></td></tr></tbody></table>'
        if '/players/' in url and url.endswith('.html'):
            return '<div>No team block</div>'
        raise RuntimeError(url)

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_TEAM_ROSTER_SIZE', 1)
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is False
    assert result['validation_report']['active_players_with_null_team_fields']
    assert __import__('json').loads((tmp_path / 'nba_players.json').read_text()) == original_players


def test_unhealthy_refresh_with_incomplete_team_coverage(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return INDEX_HTML
        if '/players/' in url and any(url.endswith(f'/{ch}/') for ch in 'bcdefghijklnmopqrstuvwxyz'):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        roster_ok = mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr='ATL', season_year=datetime.now().year)
        if url == roster_ok:
            return '<table id="roster"><tbody><tr><td data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></td></tr></tbody></table>'
        if '/teams/' in url and url.endswith('.html'):
            raise RuntimeError('team roster failed')
        if '/players/' in url and url.endswith('.html'):
            return PLAYER_HTML
        raise RuntimeError(url)

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')
    monkeypatch.setattr(mod, 'NBA_REFRESH_REPORT_PATH', tmp_path / 'nba_players.refresh_report.json')
    monkeypatch.setattr(mod, 'MINIMUM_REASONABLE_FINAL_PLAYER_COUNT', 1)
    monkeypatch.setattr(mod, 'MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT', 10000)

    result = refresh_nba_identity_from_basketball_reference()
    assert result['healthy'] is False
    assert 'not all teams contributed roster players' in result['validation_report']['health_reasons']
