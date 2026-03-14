#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import ReadTimeout, RequestException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fuzzing.slip_fuzzer import FuzzCase, FuzzRunner, persist_failure_cases, write_report
from tests.fuzzing.slip_fuzzer import FuzzIssue

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
    parser.add_argument('--timeout', type=int, default=20)
    return parser.parse_args()


def _request_exception_issue(seed: int, case: FuzzCase, exc: RequestException) -> FuzzIssue:
    return FuzzIssue(
        seed=seed,
        case_id=case.case_id,
        mode=case.mode,
        input_text=case.text,
        bet_date=case.bet_date,
        issue_type='request_exception',
        details={
            'exception_class': exc.__class__.__name__,
            'exception_message': str(exc),
        },
        response_snapshot=None,
    )


def _check_determinism_safe(
    *,
    runner: FuzzRunner,
    case: FuzzCase,
    submitter: Any,
    runs: int,
    seed: int,
) -> tuple[list[FuzzIssue], list[FuzzIssue], int, int]:
    observed: list[tuple[int, str, tuple[tuple[str, str], ...]]] = []
    request_failures: list[FuzzIssue] = []
    request_exception_count = 0
    timeout_exception_count = 0

    for _ in range(runs):
        try:
            status, body = submitter(case)
        except RequestException as exc:
            issue = _request_exception_issue(seed, case, exc)
            request_failures.append(issue)
            request_exception_count += 1
            if isinstance(exc, ReadTimeout):
                timeout_exception_count += 1
            continue

        if not isinstance(body, dict):
            continue
        parlay = str(body.get('parlay_result'))
        parse_conf = str(body.get('parse_confidence'))
        legs: list[tuple[str, str]] = []
        for item in body.get('legs', []):
            if isinstance(item, dict):
                legs.append((str(item.get('result')), str(item.get('matched_event'))))
        observed.append((status, f'{parlay}:{parse_conf}', tuple(legs)))

    nondeterminism: list[FuzzIssue] = []
    if observed:
        first = observed[0]
        if any(sample != first for sample in observed[1:]):
            nondeterminism.append(
                FuzzIssue(
                    seed=runner.seed,
                    case_id=case.case_id,
                    mode=case.mode,
                    input_text=case.text,
                    bet_date=case.bet_date,
                    issue_type='nondeterministic_response',
                    details={'observed_runs': len(observed)},
                    response_snapshot={'observed': observed},
                )
            )

    return nondeterminism, request_failures, request_exception_count, timeout_exception_count


def main() -> int:
    args = parse_args()

    if args.replay:
        return _replay_case(args.url, args.replay)

    runner = FuzzRunner(seed=args.seed, mode=args.mode, min_legs=args.min_legs, max_legs=args.max_legs)

    def submitter(case: FuzzCase) -> tuple[int, dict[str, Any] | None]:
        return _post_case(args.url, case, timeout=args.timeout)

    outcomes: list = []
    suspicious: list = []
    hard_failures: list = []
    request_exception_count = 0
    timeout_exception_count = 0

    for idx in range(args.count):
        case = runner.generate_case(idx)
        if args.case and args.case not in case.case_id:
            continue
        try:
            status_code, response = submitter(case)
        except RequestException as exc:
            issue = _request_exception_issue(args.seed, case, exc)
            from tests.fuzzing.slip_fuzzer import FuzzOutcome  # local import keeps script startup tiny

            outcome = FuzzOutcome(case=case, status_code=0, response=None, hard_failure=True, issues=[issue])
            outcomes.append(outcome)
            hard_failures.append(issue)
            request_exception_count += 1
            if isinstance(exc, ReadTimeout):
                timeout_exception_count += 1
            if args.fail_fast:
                break
            continue

        case_issues = runner.checker.evaluate(seed=args.seed, case=case, status_code=status_code, response=response)

        from tests.fuzzing.slip_fuzzer import FuzzOutcome  # local import keeps script startup tiny

        outcome = FuzzOutcome(case=case, status_code=status_code, response=response, hard_failure=status_code != 200, issues=case_issues)
        outcomes.append(outcome)

        if status_code != 200:
            hard_failures.extend(case_issues)
        else:
            suspicious.extend(case_issues)
            nondeterminism, determinism_request_failures, det_req_count, det_timeout_count = _check_determinism_safe(
                runner=runner,
                case=case,
                submitter=submitter,
                runs=args.determinism_checks + 1,
                seed=args.seed,
            )
            hard_failures.extend(nondeterminism)
            hard_failures.extend(determinism_request_failures)
            request_exception_count += det_req_count
            timeout_exception_count += det_timeout_count

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
    print(f'Request exceptions: {request_exception_count}')
    print(f'Timeout exceptions: {timeout_exception_count}')
    if hard_failures:
        top = Counter(issue.issue_type for issue in hard_failures)
        print('Top hard-failure types:')
        for issue_type, count in top.most_common(5):
            print(f'  - {issue_type}: {count}')

    return 0 if not hard_failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
