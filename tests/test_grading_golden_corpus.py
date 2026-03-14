from __future__ import annotations

import pytest

from app.services.slip_fingerprint import reset_slip_hash_index
from tests.grading_corpus_framework import assert_case, high_value_case_corpus, run_case


@pytest.mark.parametrize('case', high_value_case_corpus(), ids=lambda case: case.name)
def test_grading_high_value_golden_corpus(case) -> None:
    """First-pass golden corpus: 25 high-value cases covering risky grading behavior."""
    result = run_case(case)
    assert_case(case, result)


def test_grading_corpus_framework_supports_scalable_template_expansion() -> None:
    """Guardrail that keeps first pass intentionally small while proving generator scalability."""
    cases = high_value_case_corpus()
    assert len(cases) == 25
    generated_names = [case.name for case in cases if case.name.startswith('combo_market_')]
    assert len(generated_names) == 5


def test_alias_corpus_cases_keep_identical_slip_hashes() -> None:
    reset_slip_hash_index()
    alias_case = next(case for case in high_value_case_corpus() if case.name == 'alias_name_shai_settles')
    canonical_case = next(case for case in high_value_case_corpus() if case.name == 'canonical_name_shai_settles')

    alias_result = run_case(alias_case)
    canonical_result = run_case(canonical_case)

    assert alias_result.slip_hash == canonical_result.slip_hash
