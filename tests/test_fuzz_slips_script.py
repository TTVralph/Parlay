from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import requests


def _load_script_module():
    spec = importlib.util.spec_from_file_location('fuzz_slips_script', Path('scripts/fuzz_slips.py'))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_timeout_is_recorded_as_hard_failure(monkeypatch):
    module = _load_script_module()

    args = argparse.Namespace(
        url='http://127.0.0.1:8000/check-slip',
        count=1,
        seed=42,
        mode='mixed',
        max_legs=1,
        min_legs=1,
        case='',
        output='reports/ignored.json',
        fail_fast=False,
        replay='',
        determinism_checks=0,
        timeout=20,
    )

    monkeypatch.setattr(module, 'parse_args', lambda: args)

    def _raise_timeout(*_args, **_kwargs):
        raise requests.exceptions.ReadTimeout('simulated timeout')

    monkeypatch.setattr(module.requests, 'post', _raise_timeout)

    captured: dict = {}

    def _capture_report(path, *, seed, mode, outcomes, suspicious, hard_failures):
        captured['path'] = path
        captured['seed'] = seed
        captured['mode'] = mode
        captured['outcomes'] = outcomes
        captured['suspicious'] = suspicious
        captured['hard_failures'] = hard_failures

    monkeypatch.setattr(module, 'write_report', _capture_report)
    monkeypatch.setattr(module, 'persist_failure_cases', lambda *_a, **_k: None)

    exit_code = module.main()

    assert exit_code == 1
    assert captured['seed'] == 42
    assert captured['mode'] == 'mixed'
    assert len(captured['outcomes']) == 1
    assert len(captured['suspicious']) == 0
    assert len(captured['hard_failures']) == 1

    issue = captured['hard_failures'][0]
    assert issue.issue_type == 'request_exception'
    assert issue.case_id
    assert issue.seed == 42
    assert issue.mode
    assert issue.input_text
    assert issue.bet_date
    assert issue.details['exception_class'] == 'ReadTimeout'
    assert 'simulated timeout' in issue.details['exception_message']
