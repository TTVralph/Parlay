from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

import app.main as main_module
from app.grader import grade_text
from app.providers.sample_provider import SampleResultsProvider


client = TestClient(main_module.app)


def test_ambiguous_player_prop_goes_to_needs_review() -> None:
    result = grade_text('Jamal Murray over 2.5 threes', provider=SampleResultsProvider(), posted_at=None)
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'
    assert any('multiple possible games' in note.lower() for note in result.legs[0].leg.notes)


def test_ambiguous_team_moneyline_goes_to_needs_review() -> None:
    result = grade_text('Denver ML', provider=SampleResultsProvider(), posted_at=None)
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'
    assert any('multiple possible games' in note.lower() for note in result.legs[0].leg.notes)


def test_posted_at_context_allows_confident_match() -> None:
    posted_at = datetime.fromisoformat('2026-03-09T19:00:00')
    result = grade_text('Denver ML', provider=SampleResultsProvider(), posted_at=posted_at)
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'


def test_public_check_returns_clear_ambiguity_warning(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())
    resp = client.post('/check-slip', json={'text': 'Jamal Murray over 2.5 threes'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'needs_review'
    assert body['grading_warning'] == 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'
