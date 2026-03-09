from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
import logging
from pathlib import Path
import random
import re
import socket
import time
import unicodedata
from urllib import error, request

SPORTS_REFERENCE_SITE = 'basketball-reference'
BASKETBALL_REFERENCE_ROOT = 'https://www.basketball-reference.com'
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
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_REQUEST_DELAY_SECONDS = 0.1
DEFAULT_REQUEST_JITTER_SECONDS = 0.05
DEFAULT_BACKOFF_SECONDS = (2.0, 5.0, 10.0, 20.0)
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

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


class SportsReferenceFetcher:
    def __init__(
        self,
        *,
        request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        request_jitter_seconds: float = DEFAULT_REQUEST_JITTER_SECONDS,
        backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.request_timeout_seconds = request_timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.request_jitter_seconds = request_jitter_seconds
        self.backoff_seconds = backoff_seconds
        self.user_agent = user_agent
        self._response_cache: dict[str, str] = {}
        self._last_request_started_at: float | None = None

    def _apply_throttle(self) -> None:
        if self._last_request_started_at is None:
            return
        target_delay = self.request_delay_seconds + random.uniform(0, self.request_jitter_seconds)
        elapsed = time.monotonic() - self._last_request_started_at
        if elapsed < target_delay:
            sleep_for = target_delay - elapsed
            logger.info('Throttling outbound request for %.2fs', sleep_for)
            time.sleep(sleep_for)

    @staticmethod
    def _retry_after_seconds(headers: object) -> float | None:
        retry_after_value = getattr(headers, 'get', lambda _key, _default=None: None)('Retry-After')
        if not retry_after_value:
            return None
        try:
            return max(float(str(retry_after_value).strip()), 0.0)
        except ValueError:
            return None

    def _retry_delay_seconds(self, attempt: int, *, status_code: int | None, retry_after_seconds: float | None) -> float:
        base_delay = self.backoff_seconds[min(attempt, len(self.backoff_seconds) - 1)]
        if status_code == 429:
            base_delay = max(base_delay, 15.0)
        if retry_after_seconds is not None:
            base_delay = max(base_delay, retry_after_seconds)
        jitter = random.uniform(0, min(self.request_jitter_seconds, 1.0))
        return base_delay + jitter

    def fetch_text(self, url: str, *, context: str, use_cache: bool = True) -> str:
        if use_cache and url in self._response_cache:
            logger.info('Cache hit for %s (%s)', url, context)
            return self._response_cache[url]

        max_attempts = max(len(self.backoff_seconds) + 1, 1)
        for attempt in range(max_attempts):
            self._apply_throttle()
            self._last_request_started_at = time.monotonic()
            req = request.Request(url, headers={'User-Agent': self.user_agent, 'Accept-Language': 'en-US,en;q=0.9'})
            try:
                with request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                    body = response.read().decode('utf-8', errors='ignore')
                    if use_cache:
                        self._response_cache[url] = body
                    return body
            except error.HTTPError as exc:
                is_retryable_status = exc.code == 429 or 500 <= exc.code < 600
                if not is_retryable_status or attempt >= (max_attempts - 1):
                    raise
                retry_after_seconds = self._retry_after_seconds(exc.headers)
                delay_seconds = self._retry_delay_seconds(attempt, status_code=exc.code, retry_after_seconds=retry_after_seconds)
                logger.warning(
                    'Request failed for %s (%s) with HTTP %s; retry %s/%s in %.2fs',
                    url,
                    context,
                    exc.code,
                    attempt + 1,
                    max_attempts - 1,
                    delay_seconds,
                )
                time.sleep(delay_seconds)
            except (error.URLError, TimeoutError, socket.timeout) as exc:
                if attempt >= (max_attempts - 1):
                    raise
                delay_seconds = self._retry_delay_seconds(attempt, status_code=None, retry_after_seconds=None)
                logger.warning(
                    'Request failed for %s (%s): %s; retry %s/%s in %.2fs',
                    url,
                    context,
                    exc,
                    attempt + 1,
                    max_attempts - 1,
                    delay_seconds,
                )
                time.sleep(delay_seconds)

        raise RuntimeError(f'Unable to fetch {url}')


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

    fetcher = SportsReferenceFetcher()

    print('Fetching teams index page...')
    failed_player_pages: list[str] = []
    failed_index_letters: list[str] = []
    try:
        teams_html = fetcher.fetch_text(TEAMS_URL, context='teams index')
        parsed_teams = _parse_teams(teams_html)
    except Exception as exc:
        logger.warning('NBA teams index fetch failed: %s', exc)
        parsed_teams = [
            TeamIdentity(
                canonical_team_id=_canonical_team_id(team_abbr),
                full_team_name=team_abbr,
                abbreviations=[team_abbr],
                aliases=[normalize_name(team_abbr)],
            )
            for team_abbr in NBA_TEAM_ABBREVIATIONS
        ]
    team_name_by_abbr = {team.abbreviations[0]: team.full_team_name for team in parsed_teams}

    previous_players_by_id = _load_existing_players()

    players_by_id: dict[str, dict[str, object]] = {}
    source_names_by_id: dict[str, set[str]] = {}
    index_player_count = 0
    roster_player_count = 0

    teams_scraped_successfully: list[str] = []
    teams_failed: list[str] = []
    roster_counts_by_team: dict[str, int] = {}
    roster_only_players_added = 0
    roster_player_ids: set[str] = set()

    for idx, team_abbr in enumerate(NBA_TEAM_ABBREVIATIONS, start=1):
        print(f'Fetching roster for team {idx}/{len(NBA_TEAM_ABBREVIATIONS)} ({team_abbr})...')
        team_name = team_name_by_abbr.get(team_abbr, team_abbr)
        try:
            roster_html = fetcher.fetch_text(
                TEAM_ROSTER_URL_TEMPLATE.format(team_abbr=team_abbr, season_year=current_year),
                context=f'team roster {team_abbr}',
            )
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
            roster_only_players_added += 1

    players = list(players_by_id.values())

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
        'failed_player_page_count': len(failed_player_pages),
        'failed_player_pages': failed_player_pages,
        'failed_alphabetical_index_letters': failed_index_letters,
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

    print(
        'NBA refresh complete: '
        f'players={len(players)} teams={len(teams)} '
        f'failed_indexes={len(failed_index_letters)} failed_player_pages={len(failed_player_pages)} '
        f'healthy={healthy}'
    )

    return {
        'players': len(players),
        'teams': len(teams),
        'last_refreshed_at': now,
        'validation_report': validation_report,
        'healthy': healthy,
    }
