from __future__ import annotations

import json

import pytest

from app.services.image_preprocessor import PreprocessedImage
from app.services.slip_parser import SlipParserService
from app.services.slip_types import ParsedSlip, ParsedSlipLeg
from app.services.vision_parser import OpenAIVisionSlipParser


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.called_json = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, _url: str, *, headers: dict, json: dict):
        self.called_json = json
        return _Resp(self.payload)


class _FailingVision:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        raise RuntimeError('500 provider timeout')


class _FakeFallback:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        return ParsedSlip(raw_text='ocr', warnings=['ocr_used'], parsed_legs=[])


def test_successful_structured_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')

    processed = PreprocessedImage(
        image_bytes=b'draftkings image bytes',
        original_width=1800,
        original_height=2600,
        processed_width=1000,
        processed_height=1400,
        crop_applied=True,
        resize_applied=True,
        compressed=False,
    )
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: processed)

    payload = {
        'output_text': json.dumps({
            'sportsbook': 'draftkings',
            'screenshot_state': 'final',
            'confidence': 'high',
            'warnings': [],
            'parsed_legs': [
                {
                    'player_name': 'Nikola Jokic',
                    'market': 'assists',
                    'line': 8.5,
                    'selection': 'over',
                    'raw_text': 'Nikola Jokic Over 8.5 Assists',
                }
            ],
        })
    }
    fake_client = _Client(payload)
    monkeypatch.setattr('app.services.vision_parser.httpx.Client', lambda timeout: fake_client)

    parsed = OpenAIVisionSlipParser().parse(b'img')

    assert parsed.sportsbook == 'draftkings'
    assert parsed.screenshot_state == 'final'
    assert parsed.confidence == 'high'
    assert len(parsed.parsed_legs) == 1
    assert parsed.parsed_legs[0].player_name == 'Nikola Jokic'
    assert parsed.preprocessing_metadata is not None


def test_live_screenshot_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    processed = PreprocessedImage(b'bet365', 1000, 1500, 1000, 1500, False, False, False)
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: processed)
    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _Client({'output_text': json.dumps({
            'sportsbook': 'bet365',
            'screenshot_state': 'live',
            'confidence': 'medium',
            'warnings': ['live indicators detected'],
            'parsed_legs': [],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')
    assert parsed.screenshot_state == 'live'


def test_unknown_screenshot_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    processed = PreprocessedImage(b'unknown', 1000, 1500, 1000, 1500, False, False, False)
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: processed)
    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _Client({'output_text': json.dumps({
            'sportsbook': 'unknown',
            'screenshot_state': 'unknown',
            'confidence': 'low',
            'warnings': ['unclear screenshot'],
            'parsed_legs': [],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')
    assert parsed.screenshot_state == 'unknown'


def test_incomplete_legs_omitted_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    processed = PreprocessedImage(b'fanduel', 1200, 2200, 1000, 1833, True, True, False)
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: processed)
    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _Client({'output_text': json.dumps({
            'sportsbook': 'fanduel',
            'screenshot_state': 'final',
            'confidence': 'medium',
            'warnings': ['omitted incomplete leg'],
            'parsed_legs': [],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')
    assert parsed.parsed_legs == []
    assert 'omitted incomplete leg' in parsed.warnings


def test_fallback_path_on_provider_failure() -> None:
    service = SlipParserService(vision_parser=_FailingVision(), ocr_fallback=_FakeFallback())

    parsed = service.parse(b'img')

    assert parsed.primary_parser_status == 'failed'
    assert parsed.fallback_parser_status == 'success'
    assert parsed.fallback_reason == 'provider_error'
    assert parsed.warnings[0] == 'fallback_reason=provider_error'


def test_preprocessing_metadata_generated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    processed = PreprocessedImage(b'prizepicks', 1080, 2400, 1000, 2200, True, True, False)
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: processed)
    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _Client({'output_text': json.dumps({
            'sportsbook': 'prizepicks_like',
            'screenshot_state': 'final',
            'confidence': 'high',
            'warnings': [],
            'parsed_legs': [],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')
    assert parsed.preprocessing_metadata == {
        'original_width': 1080,
        'original_height': 2400,
        'processed_width': 1000,
        'processed_height': 2200,
        'crop_applied': True,
        'resize_applied': True,
        'compressed': False,
    }
