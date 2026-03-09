from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass

import httpx

from .image_preprocessor import preprocess_screenshot
from .slip_types import ParsedSlip, ParsedSlipLeg

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a sportsbook slip parser.

Extract only complete player prop bet legs from the screenshot.

Rules:
- Return structured JSON only.
- Ignore odds, payout, balance, promos, buttons, headers, live score bars, and app chrome.
- Normalize markets into these exact names only:
  points, rebounds, assists, threes, steals, blocks, pra, pr, pa, ra
- Normalize selections into:
  over, under
- Preserve player_name exactly as shown in the screenshot.
- Preserve a short raw_text for each leg.
- Extract only complete, high-confidence legs.
- If a leg is incomplete or unclear, omit it and add a warning.
- If the screenshot shows LIVE, a quarter/period marker, a game clock, or in-progress indicators, set screenshot_state to "live".
- If unclear, set screenshot_state to "unknown".
- Do not guess missing values."""

_USER_PROMPT = 'Extract sportsbook player prop bet legs from this screenshot. Return only the structured output matching the schema.'

_JSON_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'sportsbook': {
            'type': 'string',
            'enum': ['bet365', 'fanduel', 'draftkings', 'prizepicks_like', 'unknown'],
        },
        'screenshot_state': {
            'type': 'string',
            'enum': ['live', 'final', 'unknown'],
        },
        'confidence': {
            'type': 'string',
            'enum': ['high', 'medium', 'low'],
        },
        'warnings': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'parsed_legs': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'player_name': {'type': 'string'},
                    'market': {
                        'type': 'string',
                        'enum': [
                            'points', 'rebounds', 'assists', 'threes',
                            'steals', 'blocks', 'pra', 'pr', 'pa', 'ra',
                        ],
                    },
                    'line': {'type': 'number'},
                    'selection': {'type': 'string', 'enum': ['over', 'under']},
                    'raw_text': {'type': 'string'},
                },
                'required': ['player_name', 'market', 'line', 'selection', 'raw_text'],
            },
        },
    },
    'required': ['sportsbook', 'screenshot_state', 'confidence', 'warnings', 'parsed_legs'],
}


@dataclass(frozen=True)
class VisionCallResult:
    payload: dict
    detected_sportsbook: str


class VisionSlipParser:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip: ...


class OpenAIVisionSlipParser:
    def __init__(self) -> None:
        self._api_key = os.getenv('OPENAI_API_KEY')
        self._model = 'gpt-4o-mini'
        self._url = os.getenv('OPENAI_RESPONSES_URL', 'https://api.openai.com/v1/responses')

    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        if not self._api_key:
            raise RuntimeError('OPENAI_API_KEY is required for vision screenshot parsing.')

        processed = preprocess_screenshot(image_bytes)
        detected_sportsbook = detect_sportsbook_layout(processed.image_bytes)

        logger.info(
            'vision_parser.start model=%s parse_mode=responses_structured preprocessing=%s detected_sportsbook=%s',
            self._model,
            processed.metadata(),
            detected_sportsbook,
        )

        try:
            result = self._call_provider(processed.image_bytes, detected_sportsbook)
            data = result.payload
        except Exception as exc:
            failure = classify_failure(exc)
            logger.warning('vision_parser.failure class=%s error=%s', failure, str(exc))
            raise RuntimeError(f'{failure}: {exc}') from exc

        parsed = ParsedSlip(
            raw_text='',
            parsed_legs=[
                ParsedSlipLeg(
                    player_name=leg['player_name'],
                    market=leg['market'],
                    line=leg['line'],
                    selection=leg['selection'],
                    raw_text=leg['raw_text'],
                )
                for leg in data['parsed_legs']
            ],
            confidence=data['confidence'],
            warnings=list(data['warnings']),
            screenshot_state=data['screenshot_state'],
            sportsbook=data['sportsbook'],
            sportsbook_layout=data['sportsbook'],
            preprocessing_metadata=processed.metadata(),
            primary_parser_status='success',
        )
        logger.info(
            'vision_parser.success model=%s parse_mode=responses_structured parser_confidence=%s detected_sportsbook=%s',
            self._model,
            parsed.confidence,
            detected_sportsbook,
        )
        return parsed

    def _call_provider(self, image_bytes: bytes, detected_sportsbook: str) -> VisionCallResult:
        image_b64 = base64.b64encode(image_bytes).decode('ascii')
        payload = {
            'model': self._model,
            'temperature': 0,
            'max_output_tokens': 500,
            'input': [{
                'role': 'system',
                'content': [{'type': 'input_text', 'text': _SYSTEM_PROMPT}],
            }, {
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': f'Detected sportsbook layout hint: {detected_sportsbook}.\n{_USER_PROMPT}'},
                    {'type': 'input_image', 'image_url': f'data:image/png;base64,{image_b64}'},
                ],
            }],
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'sportsbook_slip_parse',
                    'schema': _JSON_SCHEMA,
                    'strict': True,
                },
            },
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                self._url,
                headers={'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json'},
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()

        output_text = body.get('output_text')
        if not output_text:
            raise RuntimeError('Provider returned empty structured output.')

        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError('Failed to decode provider JSON output.') from exc

        return VisionCallResult(payload=data, detected_sportsbook=detected_sportsbook)


def classify_failure(exc: Exception) -> str:
    text = str(exc).lower()
    if 'api_key' in text or 'required' in text or '401' in text:
        return 'configuration_error'
    if isinstance(exc, httpx.HTTPStatusError):
        return 'provider_error'
    if 'decode' in text or 'json' in text or 'structured output' in text:
        return 'parse_error'
    if 'image' in text or 'too large' in text or 'unsupported' in text:
        return 'low_quality_image'
    return 'provider_error'


def detect_sportsbook_layout(image_bytes: bytes) -> str:
    try:
        text = image_bytes.decode('latin-1', errors='ignore').lower()
    except Exception:
        return 'unknown'
    if 'bet365' in text:
        return 'bet365'
    if 'fanduel' in text:
        return 'fanduel'
    if 'draftkings' in text:
        return 'draftkings'
    if 'prizepicks' in text or 'pick' in text:
        return 'prizepicks_like'
    return 'unknown'
