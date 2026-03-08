from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

import app.main as main_module
from app.grader import grade_text
from app.providers.base import EventInfo
from app.providers.sample_provider import SampleResultsProvider


client = TestClient(main_module.app)


def test_ambiguous_player_prop_goes_to_needs_review() -> None:
    result = grade_text('Jamal Murray over 2.5 threes', provider=SampleResultsProvider(), include_historical=True)
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'
    assert any('multiple possible games' in note.lower() for note in result.legs[0].leg.notes)


def test_ambiguous_team_moneyline_goes_to_needs_review() -> None:
    result = grade_text('Denver ML', provider=SampleResultsProvider(), include_historical=True)
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'
    assert any('multiple possible games' in note.lower() for note in result.legs[0].leg.notes)


def test_posted_at_context_allows_confident_match() -> None:
    posted_at = datetime.fromisoformat('2026-03-09T19:00:00')
    result = grade_text('Denver ML', provider=SampleResultsProvider(), posted_at=posted_at)
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'


def test_public_check_returns_clear_ambiguity_warning(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())
    resp = client.post('/check-slip', json={'text': 'Jamal Murray over 2.5 threes', 'search_historical': True})
    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'needs_review'
    assert body['grading_warning'] == 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'


def test_public_check_returns_candidate_games_for_selection(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())
    resp = client.post('/check-slip', json={'text': 'Jamal Murray over 2.5 threes', 'search_historical': True})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body['legs'][0]['candidate_games']) >= 2


def test_date_of_slip_prioritizes_nearby_game(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())
    resp = client.post('/check-slip', json={'text': 'Denver ML', 'date_of_slip': '2026-03-09'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['legs'][0]['matched_event'] == 'Denver Nuggets @ Oklahoma City Thunder'


def test_selected_candidate_event_reuses_event_for_related_legs(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())
    selected = client.post(
        '/check-slip',
        json={
            'text': 'Jamal Murray over 2.5 threes\nDenver ML',
            'date_of_slip': '2026-03-09',
            'selected_event_id': 'nba-2026-03-09-okc-den',
            'search_historical': True,
        },
    )
    assert selected.status_code == 200
    body = selected.json()
    assert all(leg['matched_event'] == 'Denver Nuggets @ Oklahoma City Thunder' for leg in body['legs'])


def test_slip_date_with_moneyline_locks_player_props_to_same_event() -> None:
    posted_at = datetime.fromisoformat('2026-03-06T12:00:00')
    result = grade_text(
        'Jokic over 24.5 points\nMurray over 2.5 threes\nDenver ML',
        provider=SampleResultsProvider(),
        posted_at=posted_at,
        include_historical=True,
    )

    assert result.overall == 'lost'
    assert all(item.leg.event_id == 'nba-2026-03-06-den-nyk' for item in result.legs)
    assert all(item.leg.event_label == 'New York Knicks @ Denver Nuggets' for item in result.legs)


def test_public_check_slip_date_strict_guard_blocks_non_date_event_match(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())

    resp = client.post(
        '/check-slip',
        json={
            'text': 'Jokic over 24.5 points\nMurray over 2.5 threes\nDenver ML',
            'date_of_slip': '2026-03-06',
            'search_historical': True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'lost'
    assert all(leg['matched_event'] == 'New York Knicks @ Denver Nuggets' for leg in body['legs'])


def test_explicit_slip_date_with_no_exact_team_event_needs_review(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', SampleResultsProvider())

    resp = client.post(
        '/check-slip',
        json={
            'text': 'Denver ML',
            'date_of_slip': '2026-03-04',
            'search_historical': True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'needs_review'



class _PerLegSelectionProvider:
    def __init__(self) -> None:
        self._evt_a = EventInfo(
            event_id='evt-a',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-09T20:00:00+00:00'),
        )
        self._evt_b = EventInfo(
            event_id='evt-b',
            sport='NBA',
            home_team='Utah Jazz',
            away_team='Golden State Warriors',
            start_time=datetime.fromisoformat('2026-03-09T22:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Cam Spencer':
            return [self._evt_a, self._evt_b]
        if player == 'Stephen Curry':
            return [self._evt_b, self._evt_a]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return {
            'Cam Spencer': 'Memphis Grizzlies',
            'Stephen Curry': 'Golden State Warriors',
        }.get(player)

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return 10.0


def test_selected_candidate_event_applies_only_to_target_leg(monkeypatch) -> None:
    monkeypatch.setattr(main_module, '_public_check_provider', _PerLegSelectionProvider())
    selected = client.post(
        '/check-slip',
        json={
            'text': 'Cam Spencer over 9.5 points\nStephen Curry over 4.5 threes',
            'date_of_slip': '2026-03-09',
            'search_historical': True,
            'selected_event_by_leg_id': {'0': 'evt-a', '1': 'evt-b'},
        },
    )
    assert selected.status_code == 200
    body = selected.json()
    assert body['legs'][0]['matched_event'] == 'LA Clippers @ Memphis Grizzlies'
    assert body['legs'][1]['matched_event'] == 'Golden State Warriors @ Utah Jazz'
