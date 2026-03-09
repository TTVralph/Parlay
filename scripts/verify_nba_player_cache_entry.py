from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.sports_reference_identity import NBA_PLAYERS_CACHE_PATH, NBA_REFRESH_REPORT_PATH, normalize_name


def _read_players(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    parsed = json.loads(path.read_text())
    return parsed if isinstance(parsed, list) else []


def _read_report(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text())
    return parsed if isinstance(parsed, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect whether a player is present in final NBA cache and why.')
    parser.add_argument('player', help='Player name to inspect')
    parser.add_argument('--players-path', default=str(NBA_PLAYERS_CACHE_PATH))
    parser.add_argument('--report-path', default=str(NBA_REFRESH_REPORT_PATH))
    args = parser.parse_args()

    players = _read_players(Path(args.players_path))
    report = _read_report(Path(args.report_path))

    query = normalize_name(args.player)
    matches = [
        p
        for p in players
        if query == normalize_name(str(p.get('full_name') or ''))
        or query in (p.get('alias_keys') or [])
    ]

    payload: dict[str, object] = {
        'query': args.player,
        'query_normalized': query,
        'in_final_cache': bool(matches),
        'match_count': len(matches),
        'matches': [
            {
                'canonical_player_id': m.get('canonical_player_id'),
                'full_name': m.get('full_name'),
                'current_team_name': m.get('current_team_name'),
                'current_team_abbr': m.get('current_team_abbr'),
                'team_id': m.get('team_id'),
                'source_contributions': m.get('source_contributions'),
                'roster_data_applied': m.get('roster_data_applied'),
            }
            for m in matches
        ],
        'refresh_healthy': report.get('healthy'),
        'refresh_incomplete': report.get('refresh_incomplete'),
        'health_reasons': report.get('health_reasons') or [],
        'excluded_reason_hints': [],
    }

    if not matches:
        if report.get('roster_ids_missing_from_final'):
            payload['excluded_reason_hints'].append('one or more roster-derived players were missing from final output')
        if report.get('duplicate_canonical_ids'):
            payload['excluded_reason_hints'].append('duplicate canonical ids were detected during merge')
        if report.get('teams_failed'):
            payload['excluded_reason_hints'].append('one or more team roster pages failed during refresh')

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
