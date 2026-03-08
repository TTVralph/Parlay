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


def test_screenshot_grade_rejects_non_image_upload() -> None:
    os.environ['OCR_PROVIDER'] = 'mock'
    response = client.post(
        '/ingest/screenshot/grade',
        files={'file': ('slip.txt', io.BytesIO(b'not-an-image'), 'text/plain')},
        data={'posted_at': '2026-03-07T18:15:00'},
    )
    assert response.status_code == 400
    assert 'valid image file' in response.json()['detail'].lower()


def test_mock_ocr_screenshot_grade_fails_cleanly() -> None:
    os.environ['OCR_PROVIDER'] = 'mock'
    fake_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'0' * 32
    response = client.post(
        '/ingest/screenshot/grade',
        files={'file': ('slip.png', io.BytesIO(fake_png), 'image/png')},
        data={'posted_at': '2026-03-07T18:15:00'},
    )
    assert response.status_code == 400
    assert 'ocr is unavailable' in response.json()['detail'].lower()
