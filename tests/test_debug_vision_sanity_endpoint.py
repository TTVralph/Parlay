from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


_PNG_1X1 = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02'
    b'\x00\x00\x00\x0bIDATx\xdac\xfc\xff\x1f\x00\x03\x03\x02\x00\xee\xd9\x91d\x00\x00\x00\x00IEND\xaeB`\x82'
)


def test_debug_vision_sanity_endpoint_returns_expected_payload(monkeypatch):
    client = TestClient(app)

    class _FakeParser:
        def run_sanity_check(self, image_bytes: bytes, model_override: str | None = None):
            assert image_bytes == _PNG_1X1
            assert model_override == 'gpt-4.1-mini'
            return type('Result', (), {
                'raw_response_text': 'yes\\n3\\nJalen Brunson',
                'model_used': 'gpt-4.1-mini',
                'input_image_attached': True,
                'preprocessing_metadata': {
                    'original_width': 1080,
                    'original_height': 1920,
                    'processed_width': 1000,
                    'processed_height': 1777,
                    'crop_applied': True,
                    'crop_box': [0, 100, 1080, 1920],
                    'resize_applied': True,
                    'compressed': False,
                },
            })()

    monkeypatch.setattr('app.main.OpenAIVisionSlipParser', lambda: _FakeParser())

    response = client.post(
        '/debug/vision/sanity',
        files={'file': ('slip.png', _PNG_1X1, 'image/png')},
        data={'model': 'gpt-4.1-mini'},
    )

    assert response.status_code == 200
    body = response.json()
    assert body['raw_response_text'] == 'yes\\n3\\nJalen Brunson'
    assert body['model_used'] == 'gpt-4.1-mini'
    assert body['input_image_attached'] is True
    assert body['preprocessing_metadata']['processed_height'] == 1777


def test_debug_vision_sanity_endpoint_rejects_unsupported_model():
    client = TestClient(app)
    response = client.post(
        '/debug/vision/sanity',
        files={'file': ('slip.png', _PNG_1X1, 'image/png')},
        data={'model': 'gpt-4o'},
    )

    assert response.status_code == 400
    assert 'Unsupported model override' in response.json()['detail']
