from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
from pathlib import Path
import re
import unicodedata
from urllib import request

SPORTS_REFERENCE_SITE = 'basketball-reference'
BASKETBALL_REFERENCE_ROOT = 'https://www.basketball-reference.com'
PLAYER_INDEX_URL_TEMPLATE = BASKETBALL_REFERENCE_ROOT + '/players/{letter}/'
PLAYER_URL_TEMPLATE = BASKETBALL_REFERENCE_ROOT + '/players/{bucket}/{player_code}.html'
TEAMS_URL = BASKETBALL_REFERENCE_ROOT + '/teams/'
TEAM_ROSTER_URL_TEMPLATE = BASKETBALL_REFERENCE_ROOT + '/teams/{team_abbr}/{season_year}.html'

NBA_PLAYERS_CACHE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_players.json'
NBA_TEAMS_CACHE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_teams.json'


@dataclass(frozen=True)
class TeamIdentity:
    canonical_team_id: str
    full_team_name: str
    abbreviations: list[str]
    aliases: list[str]


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_name(name: str) -> str:
    lowered = _strip_diacritics(name).lower().strip()
    lowered = lowered.replace('&', ' and ')
    lowered = re.sub(r"[’'`´]", ' ', lowered)
    lowered = re.sub(r"[.]", '', lowered)
    lowered = re.sub(r'[^a-z0-9\s]', ' ', lowered)
    lowered = re.sub(r'\s+', ' ', lowered)
    return lowered.strip()


def _suffix_variants(name: str) -> set[str]:
    variants: set[str] = set()
    for suffix in ['Jr', 'III', 'II', 'IV', 'Sr']:
        variants.add(re.sub(rf'\b{suffix}\.?\b', suffix, name, flags=re.IGNORECASE))
        variants.add(re.sub(rf'\b{suffix}\.?\b', f'{suffix}.', name, flags=re.IGNORECASE))
        variants.add(re.sub(rf'\b{suffix}\.?\b', '', name, flags=re.IGNORECASE).strip())
    return {v.strip() for v in variants if v.strip()}


def build_alias_keys(name: str) -> list[str]:
    name = unescape(name).strip()
    aliases = {name, _strip_diacritics(name)}
    aliases.update(_suffix_variants(name))
    aliases.add(name.replace("'", ''))
    aliases.add(name.replace('’', ''))
    aliases.add(name.replace("'", ' '))
    aliases.add(name.replace('’', ' '))
    aliases.add(re.sub(r'\b([A-Za-z])\.', r'\1', name))
    aliases.add(re.sub(r'\s+', ' ', name).strip())
    normalized = {normalize_name(alias) for alias in aliases if alias}
    normalized.update(alias.replace(' ', '') for alias in list(normalized) if alias)
    normalized.update(alias.split()[-1] for alias in list(normalized) if alias and ' ' in alias)
    normalized = {item for item in normalized if item}
    return sorted(normalized)


def _fetch_text(url: str, timeout: int = 10) -> str:
    with request.urlopen(url, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='ignore')


def _parse_player_index(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<th[^>]*data-stat="player"[^>]*>\s*<a href="(/players/([a-z])/([a-z0-9]+)\.html)">([^<]+)</a>(.*?)</th>.*?<td[^>]*data-stat="year_max"[^>]*>(\d{4})</td>', re.S | re.I)
    rows: list[dict[str, str]] = []
    for href, bucket, code, name, trailing, year_max in pattern.findall(html):
        rows.append(
            {
                'player_code': code,
                'bucket': bucket,
                'full_name': unescape(name).strip(),
                'year_max': year_max,
                'raw_suffix': unescape(trailing).strip(),
                'source_url': BASKETBALL_REFERENCE_ROOT + href,
            }
        )
    return rows


def _extract_current_team_from_player_page(html: str) -> tuple[str | None, str | None, str]:
    m = re.search(r'Team:</strong>\s*<a href="/teams/([A-Z]{3})/\d{4}\.html">([^<]+)</a>', html)
    if not m:
        active = 'inactive' if 'Pronunciation:' in html or 'Career' in html else 'unknown'
        return None, None, active
    return m.group(2).strip(), m.group(1).strip(), 'active'


def _canonical_player_id(player_code: str) -> str:
    return f'nba-br-{player_code}'


def _canonical_team_id(team_abbr: str) -> str:
    return f'nba-team-{team_abbr.lower()}'


def _parse_teams(html: str) -> list[TeamIdentity]:
    links = re.findall(r'<a href="/teams/([A-Z]{3})/">([^<]+)</a>', html)
    teams: dict[str, TeamIdentity] = {}
    for abbr, name in links:
        full_name = unescape(name).strip()
        if abbr in teams:
            continue
        aliases = sorted({normalize_name(full_name), normalize_name(full_name.replace('Trail Blazers', 'Blazers'))})
        teams[abbr] = TeamIdentity(
            canonical_team_id=_canonical_team_id(abbr),
            full_team_name=full_name,
            abbreviations=[abbr],
            aliases=[alias for alias in aliases if alias],
        )
    return list(teams.values())


def _parse_team_roster(html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    roster_table = re.search(r'<table[^>]*id="roster"[^>]*>(.*?)</table>', html, re.S | re.I)
    if not roster_table:
        return rows
    pattern = re.compile(r'<a href="(/players/([a-z])/([a-z0-9]+)\.html)">([^<]+)</a>', re.I)
    for href, bucket, code, name in pattern.findall(roster_table.group(1)):
        rows.append(
            {
                'player_code': code,
                'bucket': bucket,
                'full_name': unescape(name).strip(),
                'source_url': BASKETBALL_REFERENCE_ROOT + href,
            }
        )
    return rows


def refresh_nba_identity_from_basketball_reference(*, gzip_output: bool = False) -> dict[str, str | int]:
    now = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    current_year = datetime.now(tz=timezone.utc).year

    teams_html = _fetch_text(TEAMS_URL)
    parsed_teams = _parse_teams(teams_html)
    team_name_by_abbr = {team.abbreviations[0]: team.full_team_name for team in parsed_teams}

    players_by_id: dict[str, dict[str, object]] = {}
    active_candidates: list[tuple[str, str, str]] = []
    for letter in 'abcdefghijklmnopqrstuvwxyz':
        html = _fetch_text(PLAYER_INDEX_URL_TEMPLATE.format(letter=letter))
        for row in _parse_player_index(html):
            status = 'active' if int(row['year_max']) >= (current_year - 1) else 'inactive'
            canonical_id = _canonical_player_id(row['player_code'])
            player_record = {
                'canonical_player_id': canonical_id,
                'sport': 'NBA',
                'full_name': row['full_name'],
                'normalized_name': normalize_name(row['full_name']),
                'alias_keys': build_alias_keys(row['full_name']),
                'current_team_name': None,
                'current_team_abbr': None,
                'active_status': status,
                'source_site': SPORTS_REFERENCE_SITE,
                'source_url': row['source_url'],
                'last_refreshed_at': now,
            }
            players_by_id[canonical_id] = player_record
            if status == 'active':
                active_candidates.append((row['bucket'], row['player_code'], row['full_name']))

    for team_abbr in team_name_by_abbr:
        roster_html = _fetch_text(TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=current_year))
        for row in _parse_team_roster(roster_html):
            canonical_id = _canonical_player_id(row['player_code'])
            existing = players_by_id.get(canonical_id)
            if existing is not None:
                if not existing.get('current_team_abbr'):
                    existing['current_team_abbr'] = team_abbr
                    existing['current_team_name'] = team_name_by_abbr[team_abbr]
                continue
            players_by_id[canonical_id] = {
                'canonical_player_id': canonical_id,
                'sport': 'NBA',
                'full_name': row['full_name'],
                'normalized_name': normalize_name(row['full_name']),
                'alias_keys': build_alias_keys(row['full_name']),
                'current_team_name': team_name_by_abbr[team_abbr],
                'current_team_abbr': team_abbr,
                'active_status': 'active',
                'source_site': SPORTS_REFERENCE_SITE,
                'source_url': row['source_url'],
                'last_refreshed_at': now,
            }
            active_candidates.append((row['bucket'], row['player_code'], row['full_name']))

    players = list(players_by_id.values())

    for bucket, code, _ in active_candidates:
        html = _fetch_text(PLAYER_URL_TEMPLATE.format(bucket=bucket, player_code=code))
        team_name, team_abbr, status = _extract_current_team_from_player_page(html)
        for row in players:
            if row['canonical_player_id'] == _canonical_player_id(code):
                row['current_team_name'] = team_name
                row['current_team_abbr'] = team_abbr
                row['active_status'] = status if row['active_status'] != 'inactive' else 'inactive'
                break

    teams = [
        {
            'canonical_team_id': team.canonical_team_id,
            'full_team_name': team.full_team_name,
            'abbreviations': team.abbreviations,
            'aliases': team.aliases,
            'source_site': SPORTS_REFERENCE_SITE,
            'last_refreshed_at': now,
        }
        for team in parsed_teams
    ]

    players.sort(key=lambda item: str(item.get('full_name') or ''))
    teams.sort(key=lambda item: str(item.get('full_team_name') or ''))

    NBA_PLAYERS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NBA_PLAYERS_CACHE_PATH.write_text(json.dumps(players, separators=(',', ':'), ensure_ascii=False) + '\n')
    NBA_TEAMS_CACHE_PATH.write_text(json.dumps(teams, separators=(',', ':'), ensure_ascii=False) + '\n')

    if gzip_output:
        import gzip

        with gzip.open(str(NBA_PLAYERS_CACHE_PATH) + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(players, f, separators=(',', ':'), ensure_ascii=False)
        with gzip.open(str(NBA_TEAMS_CACHE_PATH) + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(teams, f, separators=(',', ':'), ensure_ascii=False)

    return {
        'players': len(players),
        'teams': len(teams),
        'last_refreshed_at': now,
    }
