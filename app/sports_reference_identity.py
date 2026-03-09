from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import random
import re
import socket
import time
import unicodedata
from urllib import error, request
from urllib.parse import urlparse

SPORTS_REFERENCE_SITE = 'espn'
ESPN_TEAMS_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
ESPN_TEAM_ROSTER_URL_TEMPLATE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster'
ESPN_TEAM_URL_TEMPLATE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}'
ESPN_TEAM_URL_WITH_ROSTER_TEMPLATE = f'{ESPN_TEAM_URL_TEMPLATE}?enable=roster'

NBA_PLAYERS_CACHE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_players.json'
NBA_TEAMS_CACHE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_teams.json'
NBA_REFRESH_REPORT_PATH = Path(__file__).resolve().parent.parent / 'data' / 'nba_players.refresh_report.json'
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

ESPN_JSON_API_HOSTS = {'site.api.espn.com', 'site.web.api.espn.com'}


@dataclass(frozen=True)
class TeamIdentity:
    espn_team_id: str
    canonical_team_id: str
    full_team_name: str
    abbreviation: str


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
        variants.add(re.sub(rf'\b{suffix}\.??\b', suffix, name, flags=re.IGNORECASE))
        variants.add(re.sub(rf'\b{suffix}\.??\b', f'{suffix}.', name, flags=re.IGNORECASE))
        variants.add(re.sub(rf'\b{suffix}\.??\b', '', name, flags=re.IGNORECASE).strip())
    return {v.strip() for v in variants if v.strip()}


def build_alias_keys(name: str) -> list[str]:
    name = name.strip()
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
        self._response_cache: dict[str, dict[str, object]] = {}
        self._last_request_started_at: float | None = None

    def _apply_throttle(self) -> None:
        if self._last_request_started_at is None:
            return
        target_delay = self.request_delay_seconds + random.uniform(0, self.request_jitter_seconds)
        elapsed = time.monotonic() - self._last_request_started_at
        if elapsed < target_delay:
            time.sleep(target_delay - elapsed)

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

    def fetch_json(self, url: str, *, context: str, use_cache: bool = True) -> dict[str, object]:
        if use_cache and url in self._response_cache:
            return self._response_cache[url]

        max_attempts = max(len(self.backoff_seconds) + 1, 1)
        for attempt in range(max_attempts):
            self._apply_throttle()
            self._last_request_started_at = time.monotonic()
            req = request.Request(url, headers={'User-Agent': self.user_agent, 'Accept-Language': 'en-US,en;q=0.9'})
            try:
                with request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                    body = json.loads(response.read().decode('utf-8', errors='ignore'))
                    payload = body if isinstance(body, dict) else {}
                    if use_cache:
                        self._response_cache[url] = payload
                    return payload
            except (json.JSONDecodeError, ValueError):
                logger.warning('Request returned non-JSON for %s (%s)', url, context)
                return {}
            except error.HTTPError as exc:
                is_retryable_status = exc.code == 429 or 500 <= exc.code < 600
                if not is_retryable_status or attempt >= (max_attempts - 1):
                    raise
                delay_seconds = self._retry_delay_seconds(
                    attempt,
                    status_code=exc.code,
                    retry_after_seconds=self._retry_after_seconds(exc.headers),
                )
                time.sleep(delay_seconds)
            except (error.URLError, TimeoutError, socket.timeout) as exc:
                if attempt >= (max_attempts - 1):
                    raise
                delay_seconds = self._retry_delay_seconds(attempt, status_code=None, retry_after_seconds=None)
                logger.warning('Request failed for %s (%s): %s', url, context, exc)
                time.sleep(delay_seconds)

        raise RuntimeError(f'Unable to fetch {url}')

    def inspect_endpoint(self, url: str, *, context: str) -> tuple[int | None, str | None, str | None]:
        req = request.Request(url, headers={'User-Agent': self.user_agent, 'Accept-Language': 'en-US,en;q=0.9'})
        try:
            with request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                body = response.read().decode('utf-8', errors='ignore')
                return getattr(response, 'status', None), body[:500], None
        except error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else ''
            return exc.code, body[:500], str(exc)
        except Exception as exc:  # pragma: no cover - diagnostic path
            return None, None, str(exc)


def _canonical_player_id(player_id: str) -> str:
    return f'nba-espn-{player_id}'


def _canonical_team_id(team_abbr: str) -> str:
    return f'nba-team-{normalize_name(team_abbr).replace(" ", "-")}'


def _parse_teams(payload: dict[str, object]) -> list[TeamIdentity]:
    teams: list[TeamIdentity] = []
    sports = payload.get('sports', []) if isinstance(payload, dict) else []
    if not isinstance(sports, list) or not sports:
        return teams
    leagues = sports[0].get('leagues', []) if isinstance(sports[0], dict) else []
    if not isinstance(leagues, list) or not leagues:
        return teams
    team_wrappers = leagues[0].get('teams', []) if isinstance(leagues[0], dict) else []
    for wrapper in team_wrappers:
        if not isinstance(wrapper, dict):
            continue
        team = wrapper.get('team', {})
        if not isinstance(team, dict):
            continue
        team_id = str(team.get('id') or '').strip()
        full_name = str(team.get('displayName') or '').strip()
        abbreviation = str(team.get('abbreviation') or '').strip()
        if not team_id or not full_name:
            continue
        teams.append(
            TeamIdentity(
                espn_team_id=team_id,
                canonical_team_id=_canonical_team_id(abbreviation or full_name),
                full_team_name=full_name,
                abbreviation=abbreviation,
            )
        )
    return teams


def _maybe_absolute_espn_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        return ''
    if cleaned.startswith('http://') or cleaned.startswith('https://'):
        return cleaned
    if cleaned.startswith('/apis/'):
        return f'https://site.api.espn.com{cleaned}'
    return ''


def is_json_api_url(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned:
        return False
    if cleaned.startswith('/'):
        return cleaned.startswith('/apis/')

    parsed = urlparse(cleaned)
    if parsed.scheme not in {'http', 'https'}:
        return False
    if (parsed.hostname or '').lower() not in ESPN_JSON_API_HOSTS:
        return False
    return parsed.path.startswith('/apis/')


def _extract_roster_reference_urls(payload: object) -> list[str]:
    urls: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {'$ref', 'href', 'url'} and isinstance(value, str):
                    candidate = _maybe_absolute_espn_url(value)
                    if candidate and ('athletes' in candidate or 'roster' in candidate):
                        urls.append(candidate)
                elif key == 'link' and isinstance(value, dict):
                    href = value.get('href')
                    if isinstance(href, str):
                        candidate = _maybe_absolute_espn_url(href)
                        if candidate and ('athletes' in candidate or 'roster' in candidate):
                            urls.append(candidate)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return list(dict.fromkeys(urls))


def _parse_team_roster(
    payload: dict[str, object],
    team: TeamIdentity,
    *,
    source_url: str,
) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    reference_urls: list[str] = []
    athletes = payload.get('athletes', []) if isinstance(payload, dict) else []
    for athlete in athletes:
        if not isinstance(athlete, dict):
            continue
        player_rows = athlete.get('items') if isinstance(athlete.get('items'), list) else [athlete]
        for player in player_rows:
            if not isinstance(player, dict):
                continue
            player_id = str(player.get('id') or '').strip()
            full_name = str(player.get('displayName') or player.get('fullName') or '').strip()
            if player_id and full_name:
                rows.append(
                    {
                        'player_id': player_id,
                        'full_name': full_name,
                        'active_status': 'inactive' if str(player.get('status', {}).get('type', {}).get('name') or '').lower() == 'inactive' else 'active',
                        'source_url': source_url,
                        'current_team_name': team.full_team_name,
                        'current_team_abbr': team.abbreviation,
                        'team_id': team.canonical_team_id,
                    }
                )
            reference_urls.extend(_extract_roster_reference_urls(player))
        reference_urls.extend(_extract_roster_reference_urls(athlete))

    if not rows:
        for key in ('items', 'athlete', 'player'):
            nested = payload.get(key)
            if isinstance(nested, list):
                for player in nested:
                    if not isinstance(player, dict):
                        continue
                    player_id = str(player.get('id') or '').strip()
                    full_name = str(player.get('displayName') or player.get('fullName') or '').strip()
                    if player_id and full_name:
                        rows.append(
                            {
                                'player_id': player_id,
                                'full_name': full_name,
                                'active_status': 'inactive' if str(player.get('status', {}).get('type', {}).get('name') or '').lower() == 'inactive' else 'active',
                                'source_url': source_url,
                                'current_team_name': team.full_team_name,
                                'current_team_abbr': team.abbreviation,
                                'team_id': team.canonical_team_id,
                            }
                        )

    if not rows and isinstance(payload, dict):
        player_id = str(payload.get('id') or '').strip()
        full_name = str(payload.get('displayName') or payload.get('fullName') or '').strip()
        if player_id and full_name:
            rows.append(
                {
                    'player_id': player_id,
                    'full_name': full_name,
                    'active_status': 'inactive' if str(payload.get('status', {}).get('type', {}).get('name') or '').lower() == 'inactive' else 'active',
                    'source_url': source_url,
                    'current_team_name': team.full_team_name,
                    'current_team_abbr': team.abbreviation,
                    'team_id': team.canonical_team_id,
                }
            )

    reference_urls.extend(_extract_roster_reference_urls(payload))
    return rows, list(dict.fromkeys(reference_urls))


def _resolve_team_roster(
    fetcher: SportsReferenceFetcher,
    team: TeamIdentity,
) -> tuple[list[dict[str, str]], str, list[str]]:
    endpoints_tried: list[str] = []

    def _log_endpoint_attempt(
        endpoint: str,
        *,
        skipped_non_api: bool,
        success: bool,
        players_parsed: int,
        status: int | str | None,
        exception: str | None,
        top_level_keys: list[str] | None,
    ) -> None:
        logger.info(
            'Team roster fetch team_id=%s endpoint=%s skipped_non_api=%s success=%s status=%s exception=%s top_level_keys=%s players=%s',
            team.espn_team_id,
            endpoint,
            skipped_non_api,
            success,
            status if status is not None else '-',
            exception or '-',
            ','.join(top_level_keys or []),
            players_parsed,
        )

    def _attempt_endpoint(endpoint: str, *, context: str) -> tuple[list[dict[str, str]], list[str]]:
        endpoints_tried.append(endpoint)
        try:
            payload = fetcher.fetch_json(endpoint, context=context)
        except Exception as exc:
            _log_endpoint_attempt(
                endpoint,
                skipped_non_api=False,
                success=False,
                players_parsed=0,
                status=None,
                exception=f'{type(exc).__name__}: {exc}',
                top_level_keys=None,
            )
            return [], []

        parsed, ref_urls = _parse_team_roster(payload, team, source_url=endpoint)
        _log_endpoint_attempt(
            endpoint,
            skipped_non_api=False,
            success=bool(parsed),
            players_parsed=len(parsed),
            status='ok',
            exception=None,
            top_level_keys=sorted(str(key) for key in payload.keys()) if isinstance(payload, dict) else [],
        )
        return parsed, ref_urls

    def _follow_reference_chain(seed_urls: list[str]) -> tuple[list[dict[str, str]], str]:
        pending = [url for url in seed_urls if url and url not in endpoints_tried]
        while pending:
            ref_url = pending.pop(0)
            if not is_json_api_url(ref_url):
                logger.info('Skipping non-API roster link: %s', ref_url)
                _log_endpoint_attempt(
                    ref_url,
                    skipped_non_api=True,
                    success=False,
                    players_parsed=0,
                    status=None,
                    exception='non-api-url',
                    top_level_keys=None,
                )
                continue
            parsed_ref, nested_refs = _attempt_endpoint(ref_url, context=f'team roster ref {team.espn_team_id}')
            if parsed_ref:
                return parsed_ref, ref_url
            for nested_ref in nested_refs:
                if nested_ref and nested_ref not in endpoints_tried and nested_ref not in pending:
                    pending.append(nested_ref)
        return [], ''

    roster_url = ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id=team.espn_team_id)
    team_url_with_roster = ESPN_TEAM_URL_WITH_ROSTER_TEMPLATE.format(team_id=team.espn_team_id)
    team_url = ESPN_TEAM_URL_TEMPLATE.format(team_id=team.espn_team_id)

    roster_ref_urls: list[str] = []
    team_ref_urls: list[str] = []
    for endpoint, context, ref_target in [
        (roster_url, f'team roster {team.espn_team_id}', 'roster'),
        (team_url_with_roster, f'team details with roster {team.espn_team_id}', 'team'),
        (team_url, f'team details {team.espn_team_id}', 'team'),
    ]:
        parsed, ref_urls = _attempt_endpoint(endpoint, context=context)
        if parsed:
            return parsed, endpoint, endpoints_tried
        if ref_target == 'roster':
            roster_ref_urls.extend(ref_urls)
        else:
            team_ref_urls.extend(ref_urls)

    parsed_from_refs, ref_endpoint = _follow_reference_chain(list(dict.fromkeys(team_ref_urls)))
    if parsed_from_refs:
        return parsed_from_refs, ref_endpoint, endpoints_tried

    parsed_from_refs, ref_endpoint = _follow_reference_chain(roster_ref_urls)
    if parsed_from_refs:
        return parsed_from_refs, ref_endpoint, endpoints_tried

    return [], '', endpoints_tried


def _log_sample_endpoint_inspection(fetcher: SportsReferenceFetcher, team: TeamIdentity) -> None:
    for url in [
        ESPN_TEAM_ROSTER_URL_TEMPLATE.format(team_id=team.espn_team_id),
        ESPN_TEAM_URL_TEMPLATE.format(team_id=team.espn_team_id),
    ]:
        status, preview, exc_text = fetcher.inspect_endpoint(url, context=f'endpoint inspection team {team.espn_team_id}')
        logger.info(
            'Endpoint inspection team=%s url=%s status=%s exception=%s preview=%s',
            team.espn_team_id,
            url,
            status,
            exc_text or '-',
            (preview or '').replace('\n', ' ')[:500],
        )


def refresh_nba_identity_from_basketball_reference(*, gzip_output: bool = False) -> dict[str, str | int | dict[str, object] | bool]:
    now = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    fetcher = SportsReferenceFetcher()

    failed_team_ids: list[str] = []
    roster_counts_by_team: dict[str, int] = {}
    players_by_id: dict[str, dict[str, object]] = {}

    teams_payload = fetcher.fetch_json(ESPN_TEAMS_URL, context='teams index')
    parsed_teams = _parse_teams(teams_payload)
    if parsed_teams:
        _log_sample_endpoint_inspection(fetcher, parsed_teams[0])

    for team in parsed_teams:
        parsed_roster, success_endpoint, tried_endpoints = _resolve_team_roster(fetcher, team)
        if not parsed_roster:
            failed_team_ids.append(team.espn_team_id)
            roster_counts_by_team[team.abbreviation or team.full_team_name] = 0
            logger.info(
                'Team roster fetch team_id=%s endpoint=%s failure players=0',
                team.espn_team_id,
                tried_endpoints[-1] if tried_endpoints else '-',
            )
            continue

        roster_counts_by_team[team.abbreviation or team.full_team_name] = len(parsed_roster)
        logger.info(
            'Team roster fetch team_id=%s endpoint=%s success players=%s',
            team.espn_team_id,
            success_endpoint,
            len(parsed_roster),
        )
        for row in parsed_roster:
            canonical_id = _canonical_player_id(row['player_id'])
            players_by_id[canonical_id] = {
                'canonical_player_id': canonical_id,
                'sport': 'NBA',
                'full_name': row['full_name'],
                'normalized_name': normalize_name(row['full_name']),
                'alias_keys': build_alias_keys(row['full_name']),
                'current_team_name': row['current_team_name'],
                'current_team_abbr': row['current_team_abbr'],
                'team_id': row['team_id'],
                'team_name': row['current_team_name'],
                'active_status': row['active_status'],
                'source_site': SPORTS_REFERENCE_SITE,
                'identity_source': SPORTS_REFERENCE_SITE,
                'source_url': row['source_url'],
                'last_refreshed_at': now,
                'identity_last_refreshed_at': now,
            }

    players = sorted(players_by_id.values(), key=lambda item: str(item.get('full_name') or ''))
    teams = sorted(
        [
            {
                'canonical_team_id': team.canonical_team_id,
                'full_team_name': team.full_team_name,
                'abbreviations': [team.abbreviation] if team.abbreviation else [],
                'aliases': [normalize_name(team.full_team_name)],
                'source_site': SPORTS_REFERENCE_SITE,
                'source_url': ESPN_TEAMS_URL,
                'last_refreshed_at': now,
            }
            for team in parsed_teams
        ],
        key=lambda item: str(item.get('full_team_name') or ''),
    )

    suspiciously_low_roster_counts = [
        {'team': team_name, 'roster_count': count}
        for team_name, count in sorted(roster_counts_by_team.items())
        if count < MINIMUM_REASONABLE_TEAM_ROSTER_SIZE
    ]
    health_reasons: list[str] = []
    if len(parsed_teams) == 0:
        health_reasons.append('no teams returned by ESPN teams endpoint')
    if failed_team_ids:
        health_reasons.append('one or more team roster endpoints failed')
    if suspiciously_low_roster_counts:
        health_reasons.append('one or more teams have suspiciously low roster counts')
    if len(players) < MINIMUM_REASONABLE_FINAL_PLAYER_COUNT or len(players) > MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT:
        health_reasons.append('final player count outside healthy range')

    healthy = not health_reasons
    validation_report = {
        'teams_expected': len(parsed_teams),
        'teams_scraped_successfully': len(parsed_teams) - len(failed_team_ids),
        'teams_failed': failed_team_ids,
        'players_from_roster_pages': len(players),
        'distinct_teams_covered': len([count for count in roster_counts_by_team.values() if count > 0]),
        'players_per_team': roster_counts_by_team,
        'healthy_player_count_range': {'min': MINIMUM_REASONABLE_FINAL_PLAYER_COUNT, 'max': MAXIMUM_REASONABLE_FINAL_PLAYER_COUNT},
        'total_final_player_count': len(players),
        'suspiciously_low_roster_counts': suspiciously_low_roster_counts,
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

    return {
        'players': len(players),
        'teams': len(teams),
        'last_refreshed_at': now,
        'validation_report': validation_report,
        'healthy': healthy,
    }
