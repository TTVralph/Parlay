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
<a href="/teams/WAS/">Washington Wizards</a>
<a href="/teams/CHA/">Charlotte Hornets</a>
'''

WAS_ROSTER_HTML = '''
<table id="roster"><tbody>
<tr><td data-stat="player"><a href="/players/a/alexsar01.html">Alex Sarr</a></td></tr>
<tr><td data-stat="player"><a href="/players/m/mccaija01.html">Jared McCain</a></td></tr>
</tbody></table>
'''

CHA_ROSTER_HTML = '''
<table id="roster"><tbody>
<tr><td data-stat="player"><a href="/players/s/salauti01.html">Tidjane Salaun</a></td></tr>
</tbody></table>
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


def test_refresh_merges_roster_players_not_in_index(monkeypatch, tmp_path) -> None:
    from app import sports_reference_identity as mod

    def _fake_fetch(url: str, timeout: int = 10) -> str:
        if '/players/' in url and url.endswith('/a/'):
            return INDEX_HTML
        if '/players/' in url and url.endswith('/m/'):
            return '<table></table>'
        if '/players/' in url and url.endswith('/s/'):
            return '<table></table>'
        if '/players/' in url and re_letter(url):
            return '<table></table>'
        if url == mod.TEAMS_URL:
            return TEAMS_HTML
        if url == mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr='WAS', season_year=datetime.now().year):
            return WAS_ROSTER_HTML
        if url == mod.TEAM_ROSTER_URL_TEMPLATE.format(team_abbr='CHA', season_year=datetime.now().year):
            return CHA_ROSTER_HTML
        if '/players/' in url and url.endswith('.html'):
            return PLAYER_HTML
        raise RuntimeError(url)

    def re_letter(url: str) -> bool:
        return any(url.endswith(f'/{ch}/') for ch in 'bcdefghijklnopqrtuvwxyz')

    monkeypatch.setattr(mod, '_fetch_text', _fake_fetch)
    monkeypatch.setattr(mod, 'NBA_PLAYERS_CACHE_PATH', tmp_path / 'nba_players.json')
    monkeypatch.setattr(mod, 'NBA_TEAMS_CACHE_PATH', tmp_path / 'nba_teams.json')

    result = refresh_nba_identity_from_basketball_reference()
    assert result['players'] >= 3

    data = (tmp_path / 'nba_players.json').read_text()
    assert 'Jared McCain' in data
    assert 'Tidjane Salaun' in data


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
