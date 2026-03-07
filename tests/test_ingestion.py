from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tweet_ingestion_grades_cleaned_text() -> None:
    response = client.post(
        '/ingest/tweet/grade',
        json={
            'tweet_id': '1234567890',
            'username': 'capperx',
            'text': 'PARLAY\nDenver ML\nJokic 25+ pts\n+145',
            'posted_at': '2026-03-07T18:15:00',
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body['source_type'] == 'tweet'
    assert body['source_ref'].endswith('/status/1234567890')
    assert body['cleaned_text'] == 'Denver ML\nJokic 25+ pts'
    assert body['result']['overall'] == 'cashed'


def test_mock_ocr_screenshot_grade() -> None:
    os.environ['OCR_PROVIDER'] = 'mock'
    fake_image_bytes = b'Parlay\nDenver ML\nJokic 25+ pts\n+145\n'
    response = client.post(
        '/ingest/screenshot/grade',
        files={'file': ('slip.txt', io.BytesIO(fake_image_bytes), 'text/plain')},
        data={'posted_at': '2026-03-07T18:15:00'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['source_type'] == 'screenshot'
    assert body['cleaned_text'] == 'Denver ML\nJokic 25+ pts'
    assert body['result']['overall'] == 'cashed'
