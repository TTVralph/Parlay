#!/usr/bin/env python3
"""Quick local stress utility for /check-slip.

Examples:
  python scripts/stress_check_slip.py --base-url http://127.0.0.1:8000 --runs 20
  python scripts/stress_check_slip.py --base-url http://127.0.0.1:8000 --runs 50 --concurrency 5
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPRESENTATIVE_PAYLOADS = [
    {'name': 'clean_nba', 'body': {'text': 'Jokic over 24.5 points\nDenver ML'}},
    {'name': 'long_slip', 'body': {'text': '\n'.join([f'Denver ML leg {idx}' for idx in range(1, 22)])}},
    {'name': 'per_leg_odds', 'body': {'text': 'Draymond Green Over 5.5 Assists +500\nQuentin Grimes Over 22.5 Pts + Ast +250', 'stake_amount': 50}},
    {'name': 'stake_without_odds', 'body': {'text': 'Denver ML', 'stake_amount': 20}},
    {'name': 'stake_with_odds', 'body': {'text': 'Denver ML\nOdds +150', 'stake_amount': 20}},
    {'name': 'nonsense', 'body': {'text': 'hello world\nthis is not a slip\nfoo bar baz'}},
]


@dataclass
class RunResult:
    name: str
    ok: bool
    status_code: int
    duration_ms: float
    message: str


def hit_check_slip(base_url: str, payload: dict) -> RunResult:
    started = perf_counter()
    req = Request(
        f"{base_url.rstrip('/')}/check-slip",
        data=json.dumps(payload['body']).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(req, timeout=20) as response:
            body = json.loads(response.read().decode('utf-8'))
            return RunResult(
                name=payload['name'],
                ok=bool(body.get('ok', False)),
                status_code=response.status,
                duration_ms=(perf_counter() - started) * 1000,
                message=str(body.get('message', '')),
            )
    except HTTPError as exc:
        return RunResult(payload['name'], False, exc.code, (perf_counter() - started) * 1000, f'HTTPError: {exc.reason}')
    except URLError as exc:
        return RunResult(payload['name'], False, 0, (perf_counter() - started) * 1000, f'URLError: {exc.reason}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Stress /check-slip with representative payloads.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000', help='ParlayBot base URL (default: %(default)s)')
    parser.add_argument('--runs', type=int, default=12, help='Total requests to fire (default: %(default)s)')
    parser.add_argument('--concurrency', type=int, default=1, help='Concurrent workers (default: %(default)s)')
    args = parser.parse_args()

    queue = [REPRESENTATIVE_PAYLOADS[idx % len(REPRESENTATIVE_PAYLOADS)] for idx in range(args.runs)]

    started = perf_counter()
    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [executor.submit(hit_check_slip, args.base_url, payload) for payload in queue]
        for future in as_completed(futures):
            results.append(future.result())

    elapsed_ms = (perf_counter() - started) * 1000
    status_ok = [r for r in results if r.status_code == 200]
    failures = [r for r in results if r.status_code != 200]

    print(f'Completed {len(results)} requests in {elapsed_ms:.1f}ms (concurrency={args.concurrency}).')
    print(f'HTTP 200 responses: {len(status_ok)} | non-200 responses: {len(failures)}')

    by_name: dict[str, list[RunResult]] = {}
    for row in results:
        by_name.setdefault(row.name, []).append(row)

    for name, rows in sorted(by_name.items()):
        avg_ms = sum(r.duration_ms for r in rows) / len(rows)
        ok_count = sum(1 for r in rows if r.ok)
        print(f'  - {name:<18} runs={len(rows):<3} body.ok={ok_count:<3} avg={avg_ms:>7.2f}ms')

    if failures:
        print('\nFailures:')
        for row in failures[:10]:
            print(f'  * {row.name}: status={row.status_code} msg={row.message}')


if __name__ == '__main__':
    main()
