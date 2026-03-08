from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.providers.sample_provider import SampleResultsProvider


client = TestClient(main_module.app)


def test_check_slip_uses_public_provider_and_maps_pending_to_still_live(monkeypatch) -> None:
    class LiveOnlyProvider(SampleResultsProvider):
        def get_event_status(self, event_id: str):
            return 'live'

        def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
            return None

    monkeypatch.setattr(main_module, '_public_check_provider', LiveOnlyProvider())
    resp = client.post('/check-slip', json={'text': 'Stephen Curry over 25.5 points'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'still_live'
    assert body['legs'][0]['result'] == 'pending'
