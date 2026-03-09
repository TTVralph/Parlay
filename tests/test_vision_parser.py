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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, _url: str, *, headers: dict, json: dict):
        return _Resp(self.payload)


class _FailingVision:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        raise RuntimeError('500 provider timeout')


class _LowConfidenceVision:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        return ParsedSlip(
            raw_text='',
            parsed_legs=[],
            confidence='low',
            warnings=['Detected likely player prop rows but line/market association was unclear'],
            primary_parser_status='success',
            primary_confidence='low',
            primary_warnings=['Detected likely player prop rows but line/market association was unclear', 'Image may contain multi-line leg layout'],
            primary_detected_sportsbook='draftkings',
            primary_screenshot_state='final',
            primary_parsed_leg_count=0,
            preprocessing_metadata={
                'original_width': 1080,
                'original_height': 1920,
                'processed_width': 1000,
                'processed_height': 1777,
                'crop_applied': True,
                'crop_box': [0, 100, 1080, 1920],
                'resize_applied': True,
                'compressed': False,
            },
        )


class _FakeFallback:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        return ParsedSlip(raw_text='ocr', warnings=['ocr_used'], parsed_legs=[])


def _processed(img: bytes = b'draftkings') -> PreprocessedImage:
    return PreprocessedImage(
        image_bytes=img,
        original_width=1800,
        original_height=2600,
        processed_width=1000,
        processed_height=1400,
        crop_applied=True,
        crop_box=(10, 20, 1790, 2580),
        resize_applied=True,
        compressed=False,
    )


def test_successful_structured_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: _processed())

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
    monkeypatch.setattr('app.services.vision_parser.httpx.Client', lambda timeout: _Client(payload))

    parsed = OpenAIVisionSlipParser().parse(b'img')

    assert parsed.sportsbook == 'draftkings'
    assert parsed.primary_parser_status == 'success'
    assert parsed.primary_confidence == 'high'
    assert parsed.primary_parsed_leg_count == 1


def test_fallback_path_on_provider_failure() -> None:
    service = SlipParserService(vision_parser=_FailingVision(), ocr_fallback=_FakeFallback())
    parsed = service.parse(b'img')
    assert parsed.fallback_reason == 'vision_provider_error'
    assert parsed.primary_failure_category == 'vision_provider_error'


def test_vision_empty_parse_with_warnings_is_preserved_before_fallback() -> None:
    service = SlipParserService(vision_parser=_LowConfidenceVision(), ocr_fallback=_FakeFallback())
    parsed = service.parse(b'img')
    assert parsed.fallback_reason == 'vision_empty_parse'
    assert parsed.primary_result is not None
    assert parsed.primary_result.parsed_legs == []
    assert 'Detected likely player prop rows but line/market association was unclear' in parsed.primary_result.warnings


def test_preprocessing_metadata_generated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: _processed(b'prizepicks'))
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
        'original_width': 1800,
        'original_height': 2600,
        'processed_width': 1000,
        'processed_height': 1400,
        'crop_applied': True,
        'crop_box': [10, 20, 1790, 2580],
        'resize_applied': True,
        'compressed': False,
    }


def test_multi_line_player_prop_layout_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: _processed())
    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _Client({'output_text': json.dumps({
            'sportsbook': 'draftkings',
            'screenshot_state': 'final',
            'confidence': 'medium',
            'warnings': ['Image may contain multi-line leg layout'],
            'parsed_legs': [{
                'player_name': 'Jalen Brunson',
                'market': 'points',
                'line': 24.5,
                'selection': 'over',
                'raw_text': 'Jalen Brunson\nPoints\nOver 24.5',
            }],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')
    assert len(parsed.parsed_legs) == 1
    assert parsed.parsed_legs[0].player_name == 'Jalen Brunson'


def test_vision_low_confidence_triggers_fallback_even_with_leg() -> None:
    class _Vision:
        def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
            return ParsedSlip(
                raw_text='',
                parsed_legs=[ParsedSlipLeg(player_name='LeBron James', market='points', line=24.5, selection='over', raw_text='LeBron James\nPoints\nOver 24.5')],
                confidence='low',
                warnings=['Image may contain multi-line leg layout'],
                primary_parser_status='success',
                primary_confidence='low',
            )

    service = SlipParserService(vision_parser=_Vision(), ocr_fallback=_FakeFallback())
    parsed = service.parse(b'img')
    assert parsed.fallback_reason == 'vision_low_confidence'
    assert parsed.primary_result is not None
    assert parsed.primary_result.primary_confidence == 'low'


def test_parser_strategy_used_in_provider_payload_and_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr('app.services.vision_parser.preprocess_screenshot', lambda _b: _processed(b'bet365'))

    captured: dict = {}

    class _CaptureClient(_Client):
        def post(self, _url: str, *, headers: dict, json: dict):
            captured['payload'] = json
            return super().post(_url, headers=headers, json=json)

    monkeypatch.setattr(
        'app.services.vision_parser.httpx.Client',
        lambda timeout: _CaptureClient({'output_text': json.dumps({
            'sportsbook': 'bet365',
            'screenshot_state': 'final',
            'confidence': 'high',
            'warnings': [],
            'parsed_legs': [],
        })}),
    )

    parsed = OpenAIVisionSlipParser().parse(b'img')

    assert parsed.primary_parser_strategy_used == 'bet365'
    assert parsed.debug_artifacts is not None
    assert parsed.debug_artifacts['parser_strategy_used'] == 'bet365'
    system_text = captured['payload']['input'][0]['content'][0]['text']
    user_text = captured['payload']['input'][1]['content'][0]['text']
    assert 'Strategy: bet365 layout.' in system_text
    assert 'Parser strategy: bet365.' in user_text
