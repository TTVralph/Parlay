#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fuzzing.slip_fuzzer import FuzzCase, FuzzRunner, persist_failure_cases, write_report

DEFAULT_URL = 'http://127.0.0.1:8000/check-slip'


def _post_case(url: str, case: FuzzCase, timeout: int = 20) -> tuple[int, dict[str, Any] | None]:
    payload = {'text': case.text, 'date_of_slip': case.bet_date}
    response = requests.post(url, json=payload, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body if isinstance(body, dict) else None


def _replay_case(url: str, replay_path: str) -> int:
    payload = json.loads(Path(replay_path).read_text(encoding='utf-8'))
    text = payload.get('input_text') or payload.get('text')
    bet_date = payload.get('bet_date')
    if not text:
        raise ValueError('Replay file must include input_text or text.')

    status, body = _post_case(url, FuzzCase(case_id='replay', mode='replay', text=str(text), bet_date=str(bet_date or ''), expected_legs=1))
    print(f'Replay status: {status}')
    print(json.dumps(body, indent=2))
    return 0 if status == 200 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Monte Carlo fuzzing runner for /check-slip')
    parser.add_argument('--url', default=DEFAULT_URL)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--mode', choices=['parser', 'settlement', 'ambiguity', 'mixed'], default='mixed')
    parser.add_argument('--max-legs', type=int, default=12)
    parser.add_argument('--min-legs', type=int, default=1)
    parser.add_argument('--case', default='', help='Only run generated case ids containing this token')
    parser.add_argument('--output', default='reports/fuzz_report.json')
    parser.add_argument('--fail-fast', action='store_true')
    parser.add_argument('--replay', default='')
    parser.add_argument('--determinism-checks', type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.replay:
        return _replay_case(args.url, args.replay)

    runner = FuzzRunner(seed=args.seed, mode=args.mode, min_legs=args.min_legs, max_legs=args.max_legs)

    def submitter(case: FuzzCase) -> tuple[int, dict[str, Any] | None]:
        return _post_case(args.url, case)

    outcomes: list = []
    suspicious: list = []
    hard_failures: list = []

    for idx in range(args.count):
        case = runner.generate_case(idx)
        if args.case and args.case not in case.case_id:
            continue
        status_code, response = submitter(case)
        case_issues = runner.checker.evaluate(seed=args.seed, case=case, status_code=status_code, response=response)

        from tests.fuzzing.slip_fuzzer import FuzzOutcome  # local import keeps script startup tiny

        outcome = FuzzOutcome(case=case, status_code=status_code, response=response, hard_failure=status_code != 200, issues=case_issues)
        outcomes.append(outcome)

        if status_code != 200:
            hard_failures.extend(case_issues)
        else:
            suspicious.extend(case_issues)
            hard_failures.extend(runner._check_determinism(case, submitter, runs=args.determinism_checks + 1))

        if args.fail_fast and (case_issues or status_code != 200):
            break

    write_report(args.output, seed=args.seed, mode=args.mode, outcomes=outcomes, suspicious=suspicious, hard_failures=hard_failures)
    persist_failure_cases('reports/failures', [*hard_failures, *suspicious])

    print('Fuzz run complete')
    print(f'Mode: {args.mode}')
    print(f'Seed: {args.seed}')
    print(f'Cases run: {len(outcomes)}')
    print(f'Passed invariants: {len(outcomes) - len(suspicious) - len(hard_failures)}')
    print(f'Flagged suspicious: {len(suspicious)}')
    print(f'Hard failures: {len(hard_failures)}')

    return 0 if not hard_failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
