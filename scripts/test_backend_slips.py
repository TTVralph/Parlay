#!/usr/bin/env python3
"""Simple backend regression runner for ParlayBot /check-slip.

How to run:
  1) Start ParlayBot locally (example):
       uvicorn app.main:app --host 0.0.0.0 --port 8000
  2) In another terminal, run:
       python scripts/test_backend_slips.py

Optional:
  - Override URL with env var:
      PARLAYBOT_ENDPOINT_URL=http://127.0.0.1:8000/check-slip python scripts/test_backend_slips.py
  - Or with CLI flag:
      python scripts/test_backend_slips.py --url http://127.0.0.1:8000/check-slip
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Callable

import requests

# Easy-to-edit default endpoint.
DEFAULT_ENDPOINT_URL = os.getenv('PARLAYBOT_ENDPOINT_URL', 'http://127.0.0.1:8000/check-slip')


@dataclass(frozen=True)
class TestCase:
    name: str
    text: str
    # Optional extra request payload fields.
    extra_payload: dict[str, Any] | None = None
    check: Callable[[int, dict[str, Any] | None], tuple[bool, str]] | None = None


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _base_success(status_code: int, body: dict[str, Any] | None) -> tuple[bool, str]:
    if status_code != 200:
        return False, f'Expected HTTP 200, got {status_code}'
    if not _is_dict(body):
        return False, 'Response body is not JSON object'
    for key in ('ok', 'message', 'parlay_result', 'legs'):
        if key not in body:
            return False, f'Missing key: {key}'
    return True, 'Basic response shape looks valid'


def _expect_blank_input(status_code: int, body: dict[str, Any] | None) -> tuple[bool, str]:
    ok, reason = _base_success(status_code, body)
    if not ok:
        return ok, reason
    assert body is not None
    if body.get('ok') is not False:
        return False, 'Expected ok=false for blank input'
    msg = str(body.get('message', '')).lower()
    if 'paste at least one leg first' not in msg:
        return False, f'Unexpected message for blank input: {body.get("message")}'
    return True, 'Blank input correctly rejected'


def _expect_nonsense_or_review(status_code: int, body: dict[str, Any] | None) -> tuple[bool, str]:
    ok, reason = _base_success(status_code, body)
    if not ok:
        return ok, reason
    assert body is not None
    if body.get('ok') is False:
        return True, 'Nonsense input rejected cleanly (ok=false)'
    # If parser finds something, at least it should remain non-crashy and review-ish.
    if body.get('parlay_result') not in {'needs_review', 'still_live', 'lost', 'cashed'}:
        return False, f'Unexpected parlay_result={body.get("parlay_result")}'
    return True, 'Nonsense input handled without crashing'


def _expect_min_legs(min_legs: int) -> Callable[[int, dict[str, Any] | None], tuple[bool, str]]:
    def _check(status_code: int, body: dict[str, Any] | None) -> tuple[bool, str]:
        ok, reason = _base_success(status_code, body)
        if not ok:
            return ok, reason
        assert body is not None
        legs = body.get('legs')
        if not isinstance(legs, list):
            return False, 'legs is not a list'
        if len(legs) < min_legs:
            return False, f'Expected at least {min_legs} legs, got {len(legs)}'
        return True, f'Parsed {len(legs)} legs'

    return _check


def _expect_review_or_warning(status_code: int, body: dict[str, Any] | None) -> tuple[bool, str]:
    ok, reason = _base_success(status_code, body)
    if not ok:
        return ok, reason
    assert body is not None
    grading_warning = body.get('grading_warning')
    if body.get('parlay_result') == 'needs_review' or grading_warning:
        return True, 'Case surfaced manual-review signal'
    return False, 'Expected a review/warning signal for ambiguity case'


TEST_CASES: list[TestCase] = [
    TestCase('clean NBA 3-leg slip', 'Nikola Jokic over 24.5 points\nJamal Murray over 2.5 threes\nDenver ML', check=_expect_min_legs(3)),
    TestCase('abbreviation parsing', 'Jokic o24.5 pts\nMurray o2.5 3pm\nDEN ML', check=_expect_min_legs(2)),
    TestCase('PRA parsing', 'Nikola Jokic over 45.5 PRA', check=_expect_min_legs(1)),
    TestCase('ambiguous player (J Brown)', 'J Brown over 22.5 points', check=_expect_review_or_warning),
    TestCase('same-last-name ambiguity (J Williams)', 'J Williams over 17.5 points', check=_expect_review_or_warning),
    TestCase('A Davis ambiguity / DNP-style case', 'A Davis over 24.5 points', check=_expect_review_or_warning),
    TestCase('opponent hint', 'J Brown over 22.5 points vs Lakers', check=_expect_min_legs(1)),
    TestCase('same player multiple stats', 'Nikola Jokic over 24.5 points\nNikola Jokic over 10.5 rebounds', check=_expect_min_legs(2)),
    TestCase('duplicate identical legs', 'Denver ML\nDenver ML', check=_expect_min_legs(2)),
    TestCase('unsupported mixed sport', 'Nikola Jokic over 24.5 points\nPatrick Mahomes over 1.5 passing touchdowns', check=_expect_min_legs(1)),
    TestCase('nonsense input', 'asdf qwer zxcv\nnot a real betting slip\n???', check=_expect_nonsense_or_review),
    TestCase('blank input', '   ', check=_expect_blank_input),
]


def run_case(endpoint_url: str, case: TestCase, timeout_seconds: int = 20) -> tuple[bool, str]:
    payload = {'text': case.text}
    if case.extra_payload:
        payload.update(case.extra_payload)

    print(f'\n=== {case.name} ===')

    try:
        response = requests.post(endpoint_url, json=payload, timeout=timeout_seconds)
    except requests.RequestException as exc:
        print('HTTP status: (request failed)')
        return False, f'Request failed: {exc}'

    print(f'HTTP status: {response.status_code}')

    body: dict[str, Any] | None
    try:
        parsed_json = response.json()
        body = parsed_json if isinstance(parsed_json, dict) else None
    except ValueError:
        body = None

    if case.check is None:
        passed, reason = _base_success(response.status_code, body)
    else:
        passed, reason = case.check(response.status_code, body)

    print(f"Result: {'PASS' if passed else 'FAIL'} - {reason}")
    return passed, reason


def main() -> int:
    parser = argparse.ArgumentParser(description='Run simple /check-slip backend regression cases.')
    parser.add_argument('--url', default=DEFAULT_ENDPOINT_URL, help='Full /check-slip endpoint URL.')
    args = parser.parse_args()

    print(f'Using endpoint: {args.url}')
    passed = 0

    for case in TEST_CASES:
        case_passed, _ = run_case(args.url, case)
        if case_passed:
            passed += 1

    total = len(TEST_CASES)
    print(f'\nSummary: {passed}/{total} passed')
    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
