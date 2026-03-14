from __future__ import annotations

from tests.fuzzing.slip_fuzzer import FuzzCase, FuzzRunner


def _fake_submitter(case: FuzzCase) -> tuple[int, dict]:
    lines = [line for line in case.text.splitlines() if line.strip() and 'sgp' not in line.lower() and 'odds' not in line.lower()]
    legs = [
        {
            'leg': line,
            'result': 'review' if ' j ' in f' {line.lower()} ' else 'win',
            'line': 10.5,
            'normalized_market': 'player_points',
            'actual_value': 12.0,
            'matched_event': 'LAL @ DEN',
        }
        for line in lines
    ]
    parlay_result = 'needs_review' if any(leg['result'] == 'review' for leg in legs) else 'cashed'
    return 200, {
        'ok': True,
        'message': 'ok',
        'legs': legs,
        'parsed_legs': [leg['leg'] for leg in legs],
        'parse_warning': None,
        'grading_warning': None,
        'parlay_result': parlay_result,
        'parse_confidence': 'medium',
    }


def test_fuzz_smoke_mixed_cases() -> None:
    runner = FuzzRunner(seed=20260314, mode='mixed', min_legs=1, max_legs=8)
    outcomes, suspicious, hard_failures = runner.run_cases(count=150, submitter=_fake_submitter, determinism_checks=1)

    assert len(outcomes) == 150
    assert not hard_failures
    assert len(suspicious) <= 20
