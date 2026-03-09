from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import request

TEAMS_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
TEAM_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}'
KEY_HINTS = {'roster', 'athletes', 'items', 'href', '$ref', 'url', 'links'}


def fetch_with_meta(url: str) -> tuple[Any, int | None, str | None]:
    req = request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    with request.urlopen(req, timeout=20) as response:
        content_type = response.headers.get('Content-Type')
        status = getattr(response, 'status', None)
        raw = response.read().decode('utf-8', errors='ignore')
    return json.loads(raw), status, content_type


def search_hints(node: Any, path: str = '$') -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f'{path}.{key}'
            if key.lower() in KEY_HINTS or any(h in key.lower() for h in ('roster', 'athlete', 'link', 'href', 'ref', 'url')):
                preview = value if isinstance(value, (str, int, float, bool)) else type(value).__name__
                hits.append((next_path, key, str(preview)[:200]))
            hits.extend(search_hints(value, next_path))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits.extend(search_hints(item, f'{path}[{i}]'))
    return hits


def parse_player_counts(payload: Any) -> dict[str, int]:
    counts = {'athletes_items': 0, 'athletes_flat': 0, 'items_top_level': 0}
    if not isinstance(payload, dict):
        return counts
    athletes = payload.get('athletes')
    if isinstance(athletes, list):
        for athlete in athletes:
            if isinstance(athlete, dict):
                items = athlete.get('items')
                if isinstance(items, list):
                    counts['athletes_items'] += sum(1 for item in items if isinstance(item, dict) and (item.get('id') and (item.get('displayName') or item.get('fullName'))))
                elif athlete.get('id') and (athlete.get('displayName') or athlete.get('fullName')):
                    counts['athletes_flat'] += 1
    items = payload.get('items')
    if isinstance(items, list):
        counts['items_top_level'] = sum(1 for item in items if isinstance(item, dict) and (item.get('id') and (item.get('displayName') or item.get('fullName'))))
    return counts


def main() -> None:
    try:
        teams_payload, status, content_type = fetch_with_meta(TEAMS_URL)
    except Exception as exc:
        print(f'failed to fetch teams endpoint: {exc}')
        return
    teams = teams_payload.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
    first_team = teams[0]['team']
    team_id = str(first_team.get('id'))
    print(f'teams status={status} content_type={content_type}')
    print(f'first team id={team_id} abbr={first_team.get("abbreviation")} name={first_team.get("displayName")}')

    team_payload, t_status, t_type = fetch_with_meta(TEAM_URL.format(team_id=team_id))
    team_dump = Path(f'tmp_espn_team_{team_id}.json')
    team_dump.write_text(json.dumps(team_payload, indent=2, ensure_ascii=False) + '\n')
    print(f'team status={t_status} content_type={t_type}')
    print(f'saved team payload: {team_dump}')
    print('team top-level keys:', sorted(team_payload.keys()) if isinstance(team_payload, dict) else [])

    hits = search_hints(team_payload)
    print(f'hint matches: {len(hits)}')
    for path, key, preview in hits[:120]:
        print(f'  {path} key={key} value={preview}')

    roster_urls = []
    for _, key, value in hits:
        if key.lower() in {'href', '$ref', 'url'} and ('athletes' in value or 'roster' in value):
            roster_urls.append(value)
    roster_urls.append(TEAM_URL.format(team_id=team_id) + '?enable=roster')

    deduped: list[str] = []
    for url in roster_urls:
        if url not in deduped:
            deduped.append(url)

    for idx, roster_url in enumerate(deduped, start=1):
        if not roster_url.startswith('http'):
            continue
        print(f'roster candidate #{idx}: {roster_url}')
        try:
            roster_payload, r_status, r_type = fetch_with_meta(roster_url)
        except Exception as exc:
            print(f'  fetch failed: {exc}')
            continue
        roster_dump = Path(f'tmp_espn_roster_{team_id}_{idx}.json')
        roster_dump.write_text(json.dumps(roster_payload, indent=2, ensure_ascii=False) + '\n')
        print(f'  status={r_status} content_type={r_type}')
        print(f'  saved roster payload: {roster_dump}')
        print(f'  top-level keys: {sorted(roster_payload.keys()) if isinstance(roster_payload, dict) else []}')
        print(f'  player counts: {parse_player_counts(roster_payload)}')


if __name__ == '__main__':
    main()
