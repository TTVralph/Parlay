from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
import logging
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
NBA_REFRESH_REPORT_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_players.refresh_report.json'
NBA_TEAM_ABBREVIATIONS = (
    'ATL', 'BOS', 'BRK', 'CHO', 'CHI', 'CLE', 'DAL', 'DEN', 'DET', 'GSW',
    'HOU', 'IND', 'LAC', 'LAL', 'MEM', 'MIA', 'MIL', 'MIN', 'NOP', 'NYK',
    'OKC', 'ORL', 'PHI', 'PHO', 'POR', 'SAC', 'SAS', 'TOR', 'UTA', 'WAS',
)
MINIMUM_REASONABLE_TEAM_ROSTER_SIZE = 8
MINIMUM_REASONABLE_FINAL_PLAYER_COUNT = 350
MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT = 700

logger = logging.getLogger(__name__)


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


def _load_existing_players() -> dict[str, dict[str, object]]:
    if not NBA_PLAYERS_CACHE_PATH.exists():
        return {}
    try:
        parsed = json.loads(NBA_PLAYERS_CACHE_PATH.read_text())
    except Exception:
        return {}
    if not isinstance(parsed, list):
        return {}
    output: dict[str, dict[str, object]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            continue
        canonical_id = str(row.get('canonical_player_id') or '').strip()
        if canonical_id:
            output[canonical_id] = row
    return output


def refresh_nba_identity_from_basketball_reference(*, gzip_output: bool = False) -> dict[str, str | int | dict[str, object] | bool]:
    now = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    current_year = datetime.now(tz=timezone.utc).year

    teams_html = _fetch_text(TEAMS_URL)
    parsed_teams = _parse_teams(teams_html)
    team_name_by_abbr = {team.abbreviations[0]: team.full_team_name for team in parsed_teams}

    previous_players_by_id = _load_existing_players()

    players_by_id: dict[str, dict[str, object]] = {}
    source_names_by_id: dict[str, set[str]] = {}
    index_player_count = 0
    roster_player_count = 0
    active_candidates: list[tuple[str, str, str]] = []
    for letter in 'abcdefghijklmnopqrstuvwxyz':
        html = _fetch_text(PLAYER_INDEX_URL_TEMPLATE.format(letter=letter))
        for row in _parse_player_index(html):
            index_player_count += 1
            status = 'active' if int(row['year_max']) >= (current_year - 1) else 'inactive'
            canonical_id = _canonical_player_id(row['player_code'])
            source_names_by_id.setdefault(canonical_id, set()).add(str(row['full_name']))
            players_by_id[canonical_id] = {
                'canonical_player_id': canonical_id,
                'sport': 'NBA',
                'full_name': row['full_name'],
                'normalized_name': normalize_name(row['full_name']),
                'alias_keys': build_alias_keys(row['full_name']),
                'current_team_name': None,
                'current_team_abbr': None,
                'team_id': None,
                'team_name': None,
                'active_status': status,
                'source_site': SPORTS_REFERENCE_SITE,
                'identity_source': SPORTS_REFERENCE_SITE,
                'source_url': row['source_url'],
                'source_contributions': ['index'],
                'roster_data_applied': False,
                'last_refreshed_at': now,
                'identity_last_refreshed_at': now,
            }
            if status == 'active':
                active_candidates.append((row['bucket'], row['player_code'], row['full_name']))

    teams_scraped_successfully: list[str] = []
    teams_failed: list[str] = []
    roster_counts_by_team: dict[str, int] = {}
    roster_only_players_added = 0
    roster_player_ids: set[str] = set()

    for team_abbr in NBA_TEAM_ABBREVIATIONS:
        team_name = team_name_by_abbr.get(team_abbr, team_abbr)
        try:
            roster_html = _fetch_text(TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=current_year))
        except Exception as exc:
            teams_failed.append(team_abbr)
            roster_counts_by_team[team_abbr] = 0
            logger.warning('NBA roster import failed for %s: %s', team_abbr, exc)
            continue

        parsed_roster = _parse_team_roster(roster_html)
        teams_scraped_successfully.append(team_abbr)
        roster_counts_by_team[team_abbr] = len(parsed_roster)
        logger.info('NBA roster import succeeded for %s players=%s', team_abbr, len(parsed_roster))

        for row in parsed_roster:
            roster_player_count += 1
            canonical_id = _canonical_player_id(row['player_code'])
            roster_player_ids.add(canonical_id)
            source_names_by_id.setdefault(canonical_id, set()).add(str(row['full_name']))
            existing = players_by_id.get(canonical_id)
            if existing is not None:
                existing['current_team_abbr'] = team_abbr
                existing['current_team_name'] = team_name
                existing['team_id'] = _canonical_team_id(team_abbr)
                existing['team_name'] = team_name
                contributions = set(existing.get('source_contributions') or [])
                contributions.add('roster')
                existing['source_contributions'] = sorted(contributions)
                existing['roster_data_applied'] = True
                continue

            players_by_id[canonical_id] = {
                'canonical_player_id': canonical_id,
                'sport': 'NBA',
                'full_name': row['full_name'],
                'normalized_name': normalize_name(row['full_name']),
                'alias_keys': build_alias_keys(row['full_name']),
                'current_team_name': team_name,
                'current_team_abbr': team_abbr,
                'team_id': _canonical_team_id(team_abbr),
                'team_name': team_name,
                'active_status': 'active',
                'source_site': SPORTS_REFERENCE_SITE,
                'identity_source': SPORTS_REFERENCE_SITE,
                'source_url': row['source_url'],
                'source_contributions': ['roster'],
                'roster_data_applied': True,
                'last_refreshed_at': now,
                'identity_last_refreshed_at': now,
            }
            active_candidates.append((row['bucket'], row['player_code'], row['full_name']))
            roster_only_players_added += 1

    players = list(players_by_id.values())

    for bucket, code, _ in active_candidates:
        html = _fetch_text(PLAYER_URL_TEMPLATE.format(bucket=bucket, player_code=code))
        team_name, team_abbr, status = _extract_current_team_from_player_page(html)
        for row in players:
            if row['canonical_player_id'] == _canonical_player_id(code):
                is_rostered = bool(row.get('roster_data_applied'))
                if team_abbr and team_name and not is_rostered:
                    row['current_team_name'] = team_name
                    row['current_team_abbr'] = team_abbr
                    row['team_id'] = _canonical_team_id(team_abbr)
                    row['team_name'] = team_name
                row['active_status'] = status if row['active_status'] != 'inactive' else 'inactive'
                break

    for row in players:
        if row.get('current_team_abbr') and not row.get('team_id'):
            row['team_id'] = _canonical_team_id(str(row['current_team_abbr']))
        if row.get('current_team_name') and not row.get('team_name'):
            row['team_name'] = row['current_team_name']

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

    roster_ids_missing_from_final = sorted(roster_player_ids.difference(str(p.get('canonical_player_id') or '') for p in players))
    missing_team_assignments = sorted(str(p.get('full_name') or '') for p in players if not p.get('team_id') or not p.get('team_name'))
    active_players_with_null_team_fields = sorted(
        str(p.get('full_name') or '')
        for p in players
        if p.get('active_status') != 'inactive'
        and (not p.get('current_team_name') or not p.get('current_team_abbr') or not p.get('team_id') or not p.get('team_name'))
    )
    roster_players_with_null_team_fields = sorted(
        str(p.get('full_name') or '')
        for p in players
        if str(p.get('canonical_player_id') or '') in roster_player_ids
        and (not p.get('current_team_name') or not p.get('current_team_abbr') or not p.get('team_id') or not p.get('team_name'))
    )
    suspiciously_low_roster_counts = [
        {'team_abbr': team_abbr, 'roster_count': roster_counts_by_team.get(team_abbr, 0)}
        for team_abbr in NBA_TEAM_ABBREVIATIONS
        if roster_counts_by_team.get(team_abbr, 0) < MINIMUM_REASONABLE_TEAM_ROSTER_SIZE
    ]
    duplicate_canonical_ids = [
        {'canonical_player_id': canonical_id, 'distinct_names_seen': sorted(names)}
        for canonical_id, names in sorted(source_names_by_id.items())
        if len(names) > 1
    ]
    team_changes_from_previous = []
    for player in players:
        canonical_id = str(player.get('canonical_player_id') or '')
        previous = previous_players_by_id.get(canonical_id)
        if not previous:
            continue
        prev_abbr = str(previous.get('current_team_abbr') or '').strip()
        new_abbr = str(player.get('current_team_abbr') or '').strip()
        if prev_abbr and new_abbr and prev_abbr != new_abbr:
            team_changes_from_previous.append({'canonical_player_id': canonical_id, 'from': prev_abbr, 'to': new_abbr})

    total_teams_with_roster = len([team for team in NBA_TEAM_ABBREVIATIONS if roster_counts_by_team.get(team, 0) > 0])
    final_player_count = len(players)
    total_source_records = index_player_count + roster_player_count
    unique_ids_from_sources = len(source_names_by_id)
    players_dropped_during_merge = max(total_source_records - unique_ids_from_sources, 0)
    health_reasons: list[str] = []
    if final_player_count < MINIMUM_REASONABLE_FINAL_PLAYER_COUNT or final_player_count > MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT:
        health_reasons.append('final player count outside healthy range')
    if total_teams_with_roster != len(NBA_TEAM_ABBREVIATIONS):
        health_reasons.append('not all teams contributed roster players')
    if suspiciously_low_roster_counts:
        health_reasons.append('one or more teams have suspiciously low roster counts')
    if roster_ids_missing_from_final:
        health_reasons.append('roster-derived players missing from final output')
    if active_players_with_null_team_fields:
        health_reasons.append('active players have null team fields')
    if roster_players_with_null_team_fields:
        health_reasons.append('rostered players have null team fields')
    if duplicate_canonical_ids:
        health_reasons.append('duplicate canonical ids map to multiple distinct names')

    healthy = (
        not health_reasons
    )

    validation_report = {
        'teams_expected': len(NBA_TEAM_ABBREVIATIONS),
        'teams_scraped_successfully': teams_scraped_successfully,
        'teams_failed': teams_failed,
        'players_from_alphabetical_index': index_player_count,
        'players_from_roster_pages': roster_player_count,
        'players_dropped_during_merge': players_dropped_during_merge,
        'distinct_teams_covered': total_teams_with_roster,
        'players_per_team': {team_abbr: roster_counts_by_team.get(team_abbr, 0) for team_abbr in NBA_TEAM_ABBREVIATIONS},
        'healthy_player_count_range': {'min': MINIMUM_REASONABLE_FINAL_PLAYER_COUNT, 'max': MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT},
        'total_active_players_imported': len([p for p in players if p.get('active_status') != 'inactive']),
        'total_final_player_count': final_player_count,
        'players_missing_team': missing_team_assignments,
        'players_with_null_team_fields': len(missing_team_assignments),
        'active_players_with_null_team_fields': active_players_with_null_team_fields,
        'roster_players_with_null_team_fields': roster_players_with_null_team_fields,
        'roster_ids_missing_from_final': roster_ids_missing_from_final,
        'duplicate_canonical_ids': duplicate_canonical_ids,
        'suspiciously_low_roster_counts': suspiciously_low_roster_counts,
        'roster_only_players_added': roster_only_players_added,
        'players_whose_team_changed_during_refresh': team_changes_from_previous,
        'health_reasons': health_reasons,
        'healthy': healthy,
        'refresh_incomplete': not healthy,
    }
    NBA_REFRESH_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    NBA_REFRESH_REPORT_PATH.write_text(json.dumps(validation_report, separators=(',', ':'), ensure_ascii=False) + '\n')

    if healthy:
        NBA_PLAYERS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        NBA_PLAYERS_CACHE_PATH.write_text(json.dumps(players, separators=(',', ':'), ensure_ascii=False) + '\n')
        NBA_TEAMS_CACHE_PATH.write_text(json.dumps(teams, separators=(',', ':'), ensure_ascii=False) + '\n')

        if gzip_output:
            import gzip

            with gzip.open(str(NBA_PLAYERS_CACHE_PATH) + '.gz', 'wt', encoding='utf-8') as f:
                json.dump(players, f, separators=(',', ':'), ensure_ascii=False)
            with gzip.open(str(NBA_TEAMS_CACHE_PATH) + '.gz', 'wt', encoding='utf-8') as f:
                json.dump(teams, f, separators=(',', ':'), ensure_ascii=False)
    else:
        logger.error('NBA identity refresh unhealthy; refusing to overwrite cache files')

    if not healthy:
        logger.warning('NBA identity refresh marked incomplete: %s', json.dumps(validation_report, sort_keys=True))

    return {
        'players': len(players),
        'teams': len(teams),
        'last_refreshed_at': now,
        'validation_report': validation_report,
        'healthy': healthy,
    }
