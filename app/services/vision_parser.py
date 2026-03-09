from __future__ import annotations

import base64
import json
import os
from typing import Protocol

import httpx

from .slip_types import ParsedSlip, ParsedSlipLeg


class VisionSlipParser(Protocol):
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip: ...


class OpenAIVisionSlipParser:
    def __init__(self) -> None:
        self._api_key = os.getenv('OPENAI_API_KEY')
        self._model = os.getenv('OPENAI_VISION_MODEL', 'gpt-4.1-mini')
        self._url = os.getenv('OPENAI_RESPONSES_URL', 'https://api.openai.com/v1/responses')

    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        if not self._api_key:
            raise RuntimeError('OPENAI_API_KEY is required for vision screenshot parsing.')
        image_b64 = base64.b64encode(image_bytes).decode('ascii')
        prompt = (
            'Extract sportsbook slip legs from this screenshot. Return JSON only. '
            'Be robust to crops, odds text, boosts, stake/payout clutter, and multi-leg layouts. '
            'Do not hardcode one sportsbook; detect layout when possible and set sportsbook_layout. '
            'Normalize markets (Pts->points, Reb->rebounds, Ast->assists, 3PT/3PM->threes) and selection (Over/Under). '
            'Preserve each leg raw_text. Flag ambiguity in warnings.'
        )
        schema = {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'raw_text': {'type': 'string'},
                'parsed_legs': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'properties': {
                    'sport': {'type': ['string', 'null']},
                    'player_name': {'type': ['string', 'null']},
                    'market': {'type': ['string', 'null']},
                    'line': {'type': ['number', 'null']},
                    'selection': {'type': ['string', 'null']},
                    'raw_text': {'type': 'string'},
                }, 'required': ['sport', 'player_name', 'market', 'line', 'selection', 'raw_text']}},
                'warnings': {'type': 'array', 'items': {'type': 'string'}},
                'sportsbook_layout': {'type': ['string', 'null']},
                'detected_bet_date': {'type': ['string', 'null']},
                'stake_amount': {'type': ['number', 'null']},
                'to_win_amount': {'type': ['number', 'null']},
            },
            'required': ['raw_text', 'parsed_legs', 'warnings', 'sportsbook_layout', 'detected_bet_date', 'stake_amount', 'to_win_amount'],
        }
        payload = {
            'model': self._model,
            'input': [{'role': 'user', 'content': [
                {'type': 'input_text', 'text': prompt},
                {'type': 'input_image', 'image_url': f'data:image/png;base64,{image_b64}'},
            ]}],
            'text': {'format': {'type': 'json_schema', 'name': 'slip_parse', 'schema': schema, 'strict': True}},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self._url, headers={'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json'}, json=payload)
            resp.raise_for_status()
            body = resp.json()
        output_text = body.get('output_text')
        if not output_text:
            raise RuntimeError('Vision provider returned empty output.')
        data = json.loads(output_text)
        return ParsedSlip(
            raw_text=data.get('raw_text', ''),
            parsed_legs=[ParsedSlipLeg(**leg) for leg in data.get('parsed_legs', [])],
            warnings=list(data.get('warnings') or []),
            sportsbook_layout=data.get('sportsbook_layout'),
            detected_bet_date=data.get('detected_bet_date'),
            stake_amount=data.get('stake_amount'),
            to_win_amount=data.get('to_win_amount'),
        )
