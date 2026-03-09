from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .image_preprocessor import preprocess_screenshot
from .market_registry import normalize_market as normalize_market_with_registry
from .slip_types import ParsedSlip, ParsedSlipLeg
from .vision_prompt_builder import build_vision_prompts

logger = logging.getLogger(__name__)

_JSON_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'sportsbook': {'type': 'string', 'enum': ['bet365', 'fanduel', 'draftkings', 'prizepicks_like', 'unknown']},
        'screenshot_state': {'type': 'string', 'enum': ['live', 'final', 'unknown']},
        'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        'warnings': {'type': 'array', 'items': {'type': 'string'}},
        'parsed_legs': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'player_name': {'type': 'string'},
                    'market': {'type': 'string', 'enum': ['points', 'rebounds', 'assists', 'threes', 'steals', 'blocks', 'pra', 'pr', 'pa', 'ra']},
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
    diagnostics: dict[str, Any] | None = None


class _VisionSlipLegModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    player_name: str
    market: str
    line: float
    selection: str
    raw_text: str


class _VisionSlipPayloadModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sportsbook: str
    screenshot_state: str
    confidence: str
    warnings: list[str]
    parsed_legs: list[_VisionSlipLegModel]


_MARKET_ENUM = {'points', 'rebounds', 'assists', 'threes', 'steals', 'blocks', 'pra', 'pr', 'pa', 'ra'}
_SPORTSBOOK_ENUM = {'bet365', 'fanduel', 'draftkings', 'prizepicks_like', 'unknown'}
_SCREENSHOT_STATE_ENUM = {'live', 'final', 'unknown'}
_CONFIDENCE_ENUM = {'high', 'medium', 'low'}
_SELECTION_ENUM = {'over', 'under'}

_MARKET_VARIANTS = {
    'made threes': 'threes', '3pm': 'threes', '3pt made': 'threes', 'three pointers': 'threes',
    'pts': 'points', 'reb': 'rebounds', 'ast': 'assists',
}
_SPORTSBOOK_VARIANTS = {'prizepicks': 'prizepicks_like'}
_SCREENSHOT_STATE_VARIANTS = {'in_progress': 'live'}
_CONFIDENCE_VARIANTS = {'very high': 'high', 'strong': 'high', 'moderate': 'medium', 'uncertain': 'low', 'weak': 'low'}
_LEG_LIST_KEYS = ('parsed_legs', 'players', 'bets', 'legs')


class VisionSchemaValidationError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class VisionProviderResponseError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class VisionSlipParser:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip: ...


@dataclass(frozen=True)
class VisionSanityResult:
    raw_response_text: str
    model_used: str
    input_image_attached: bool
    preprocessing_metadata: dict[str, Any]


class OpenAIVisionSlipParser:
    def __init__(self) -> None:
        self._api_key = os.getenv('OPENAI_API_KEY')
        self._model = 'gpt-4o-mini'
        self._url = os.getenv('OPENAI_RESPONSES_URL', 'https://api.openai.com/v1/responses')
        self._debug_mode = os.getenv('SCREENSHOT_DEBUG_MODE', '').lower() in {'1', 'true', 'yes', 'on'}
        self._debug_dir = Path(os.getenv('SCREENSHOT_DEBUG_DIR', 'tmp/screenshot_debug'))

    def run_sanity_check(self, image_bytes: bytes, model_override: str | None = None) -> VisionSanityResult:
        if not self._api_key:
            raise RuntimeError('OPENAI_API_KEY is required for vision screenshot parsing.')
        try:
            processed = preprocess_screenshot(image_bytes)
        except Exception as exc:
            raise RuntimeError(f'vision_preprocessing_error: {exc}') from exc

        selected_model = model_override or self._model
        body, input_image_attached = self._call_provider_sanity(processed.image_bytes, model=selected_model)

        return VisionSanityResult(
            raw_response_text=_extract_output_text(body),
            model_used=selected_model,
            input_image_attached=input_image_attached,
            preprocessing_metadata=processed.metadata(),
        )

    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        if not self._api_key:
            raise RuntimeError('OPENAI_API_KEY is required for vision screenshot parsing.')
        try:
            processed = preprocess_screenshot(image_bytes)
        except Exception as exc:
            raise RuntimeError(f'vision_preprocessing_error: {exc}') from exc

        detected_sportsbook = detect_sportsbook_layout(processed.image_bytes)
        debug_artifacts: dict[str, str] = {}
        if self._debug_mode:
            debug_artifacts.update(self._save_image_artifacts(image_bytes, processed.image_bytes, filename))

        prompt_strategy = build_vision_prompts(detected_sportsbook)
        logger.info('vision_parser.start model=%s parse_mode=responses_structured preprocessing=%s detected_sportsbook=%s parser_strategy=%s', self._model, processed.metadata(), detected_sportsbook, prompt_strategy.parser_strategy_used)

        try:
            result = self._call_provider(processed.image_bytes, detected_sportsbook, prompt_strategy, processed.metadata())
            data = result.payload
            if self._debug_mode:
                debug_artifacts.update(self._save_json_artifact(data, filename))
                raw_response = result.diagnostics.get('raw_response') if result.diagnostics else None
                if isinstance(raw_response, dict):
                    debug_artifacts.update(self._save_raw_response_artifact(raw_response, filename))
            if result.diagnostics:
                if self._debug_mode:
                    debug_artifacts.update(self._save_schema_diagnostic_artifact(result.diagnostics, filename))
                _merge_schema_diagnostics_into_artifacts(debug_artifacts, result.diagnostics)
            debug_artifacts['parser_strategy_used'] = prompt_strategy.parser_strategy_used
        except Exception as exc:
            failure = classify_failure(exc)
            diagnostics = dict(getattr(exc, 'diagnostics', {}) or {})
            diagnostics.setdefault('parser_strategy_used', prompt_strategy.parser_strategy_used)
            diagnostics.setdefault('detected_sportsbook', detected_sportsbook)
            if isinstance(exc, VisionSchemaValidationError):
                d = exc.diagnostics
                logger.warning('vision_parser.failure class=%s category=vision_schema_error path=%s message=%s excerpt=%s', failure, d.get('schema_error_path'), d.get('schema_error_message'), d.get('raw_primary_output_excerpt'))
            else:
                logger.warning('vision_parser.failure class=%s error=%s', failure, str(exc))
            wrapped = RuntimeError(f'{failure}: {exc}')
            wrapped.diagnostics = diagnostics
            raise wrapped from exc

        parsed = ParsedSlip(
            raw_text='',
            parsed_legs=[ParsedSlipLeg(player_name=leg['player_name'], market=leg['market'], line=leg['line'], selection=leg['selection'], raw_text=leg['raw_text']) for leg in data['parsed_legs']],
            confidence=data['confidence'],
            warnings=list(data['warnings']),
            screenshot_state=data['screenshot_state'],
            sportsbook=data['sportsbook'],
            sportsbook_layout=data['sportsbook'],
            preprocessing_metadata=processed.metadata(),
            primary_parser_status='success',
            primary_confidence=data['confidence'],
            primary_warnings=list(data['warnings']),
            primary_detected_sportsbook=result.detected_sportsbook,
            primary_parser_strategy_used=prompt_strategy.parser_strategy_used,
            primary_screenshot_state=data['screenshot_state'],
            primary_parsed_leg_count=len(data['parsed_legs']),
            debug_artifacts=debug_artifacts or None,
        )
        logger.info('vision_parser.success model=%s parse_mode=responses_structured parser_confidence=%s detected_sportsbook=%s parser_strategy=%s', self._model, parsed.confidence, detected_sportsbook, prompt_strategy.parser_strategy_used)
        return parsed

    def _save_image_artifacts(self, original: bytes, processed: bytes, filename: str | None) -> dict[str, str]:
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        base = (Path(filename or 'upload').stem or 'upload') + '_' + uuid4().hex[:8]
        orig_path = self._debug_dir / f'{base}_original.png'
        proc_path = self._debug_dir / f'{base}_preprocessed.png'
        orig_path.write_bytes(original)
        proc_path.write_bytes(processed)
        return {'debug_original_image_path': str(orig_path), 'debug_preprocessed_image_path': str(proc_path)}

    def _save_json_artifact(self, parsed_json: dict, filename: str | None) -> dict[str, str]:
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        base = (Path(filename or 'upload').stem or 'upload') + '_' + uuid4().hex[:8]
        parsed_path = self._debug_dir / f'{base}_primary_response.json'
        parsed_path.write_text(json.dumps(parsed_json, indent=2))
        return {'debug_primary_response_path': str(parsed_path)}

    def _save_schema_diagnostic_artifact(self, diagnostics: dict[str, Any], filename: str | None) -> dict[str, str]:
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        base = (Path(filename or 'upload').stem or 'upload') + '_' + uuid4().hex[:8]
        path = self._debug_dir / f'{base}_schema_diagnostics.json'
        path.write_text(json.dumps(diagnostics, indent=2))
        return {'debug_schema_diagnostics_path': str(path)}

    def _save_raw_response_artifact(self, payload: dict[str, Any], filename: str | None) -> dict[str, str]:
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        base = (Path(filename or 'upload').stem or 'upload') + '_' + uuid4().hex[:8]
        path = self._debug_dir / f'{base}_raw_response.json'
        path.write_text(json.dumps(payload, indent=2))
        return {'debug_raw_response_path': str(path)}

    def _call_provider(self, image_bytes: bytes, detected_sportsbook: str, prompt_strategy, preprocessing_metadata: dict[str, Any]) -> VisionCallResult:
        image_b64 = base64.b64encode(image_bytes).decode('ascii')
        user_content = [
            {'type': 'input_text', 'text': prompt_strategy.user_prompt},
            {'type': 'input_image', 'image_url': f'data:image/png;base64,{image_b64}'},
        ]
        payload = {
            'model': self._model,
            'temperature': 0,
            'max_output_tokens': 500,
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': prompt_strategy.system_prompt}]},
                {'role': 'user', 'content': user_content},
            ],
            'text': {'format': {'type': 'json_schema', 'name': 'sportsbook_slip_parse', 'schema': _JSON_SCHEMA, 'strict': True}},
        }

        has_input_image = _has_input_image(user_content)
        image_mime_type = 'image/png'
        request_diagnostics = {
            'request_model': self._model,
            'request_text_format': payload.get('text', {}).get('format'),
            'request_has_input_image': has_input_image,
            'request_image_mime_type': image_mime_type,
            'request_image_base64_size': len(image_b64),
            'request_processed_width': preprocessing_metadata.get('processed_width'),
            'request_processed_height': preprocessing_metadata.get('processed_height'),
        }
        logger.info(
            'vision_parser.request model=%s parser_strategy=%s text_format=%s input_image_present=%s image_mime=%s base64_size=%s',
            self._model,
            prompt_strategy.parser_strategy_used,
            request_diagnostics['request_text_format'],
            has_input_image,
            image_mime_type,
            len(image_b64),
        )

        if not has_input_image:
            raise VisionProviderResponseError(
                'vision_schema_error: Missing input_image in Responses API payload.',
                diagnostics={
                    'primary_failure_category': 'vision_schema_error',
                    **request_diagnostics,
                },
            )

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self._url, headers={'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json'}, json=payload)
            resp.raise_for_status()
            body = resp.json()

        response_diagnostics = _extract_response_diagnostics(body)
        diagnostics: dict[str, Any] = {
            **request_diagnostics,
            **response_diagnostics,
            'raw_response': _sanitize_response_object(body),
        }

        output_text = response_diagnostics.get('combined_output_text', '')
        if not output_text:
            if response_diagnostics.get('has_refusal'):
                raise VisionSchemaValidationError(
                    'vision_schema_error: Provider refusal returned without structured content.',
                    diagnostics={'primary_failure_category': 'vision_schema_error', 'provider_response_kind': 'provider_refusal', **diagnostics},
                )
            raise VisionSchemaValidationError(
                'vision_schema_error: Provider returned no content.',
                diagnostics={'primary_failure_category': 'vision_schema_error', 'provider_response_kind': 'provider_no_content', **diagnostics},
            )

        diagnostics['raw_primary_output'] = output_text
        diagnostics['raw_primary_output_excerpt'] = _excerpt(output_text)

        try:
            parsed_json = json.loads(output_text)
        except json.JSONDecodeError as exc:
            repaired_payload = _attempt_tolerant_json_parse(output_text)
            if repaired_payload is None:
                provider_kind = 'provider_plain_text' if response_diagnostics.get('has_any_text') else 'provider_malformed_structured_content'
                raise VisionSchemaValidationError(
                    'vision_schema_error: Failed to decode provider JSON output.',
                    diagnostics={
                        'primary_failure_category': 'vision_schema_error',
                        'provider_response_kind': provider_kind,
                        'schema_error_message': f'json_decode_error: {exc.msg}',
                        'schema_error_path': '$',
                        **diagnostics,
                    },
                ) from exc
            parsed_json = repaired_payload
            diagnostics['schema_repair_applied'] = True
            diagnostics['schema_repair_reason'] = 'manual_json_text_repair'

        strict_errors = _validate_payload(parsed_json)
        if not strict_errors:
            return VisionCallResult(payload=parsed_json, detected_sportsbook=detected_sportsbook, diagnostics=diagnostics)

        normalized = _normalize_payload(parsed_json)
        repaired_errors = _validate_payload(normalized)
        if not repaired_errors:
            logger.info('vision_parser.schema_repair_applied detected_sportsbook=%s', detected_sportsbook)
            return VisionCallResult(payload=normalized, detected_sportsbook=detected_sportsbook, diagnostics={
                'primary_failure_category': 'vision_schema_error',
                'schema_error_path': strict_errors[0]['path'],
                'schema_error_message': strict_errors[0]['message'],
                'parsed_json': parsed_json,
                'schema_validation_errors': strict_errors,
                'schema_repair_applied': True,
                **diagnostics,
            })

        diagnostics.update({'primary_failure_category': 'vision_schema_error', 'provider_response_kind': 'provider_malformed_structured_content', 'schema_error_path': repaired_errors[0]['path'], 'schema_error_message': repaired_errors[0]['message'], 'parsed_json': parsed_json, 'normalized_json': normalized, 'schema_validation_errors': repaired_errors, 'failed_fields': [err['path'] for err in repaired_errors]})
        raise VisionSchemaValidationError(f"vision_schema_error: {repaired_errors[0]['path']}: {repaired_errors[0]['message']}", diagnostics=diagnostics)

    def _call_provider_sanity(self, image_bytes: bytes, model: str) -> tuple[dict[str, Any], bool]:
        image_b64 = base64.b64encode(image_bytes).decode('ascii')
        user_content = [
            {
                'type': 'input_text',
                'text': (
                    'Answer these exactly, each on its own line, and return only the answers:\n'
                    '1) Return only yes or no: does this screenshot show a live game?\n'
                    '2) Return only the number of visible player prop rows.\n'
                    '3) Return only the top visible player name.'
                ),
            },
            {'type': 'input_image', 'image_url': f'data:image/png;base64,{image_b64}'},
        ]
        payload = {
            'model': model,
            'temperature': 0,
            'max_output_tokens': 120,
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'You are a precise vision checker. Keep answers short and literal.'}]},
                {'role': 'user', 'content': user_content},
            ],
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self._url, headers={'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json'}, json=payload)
            resp.raise_for_status()
            body = resp.json()

        return body, any(item.get('type') == 'input_image' for item in user_content)


def _has_input_image(content_items: list[dict[str, Any]]) -> bool:
    return any(item.get('type') == 'input_image' for item in content_items if isinstance(item, dict))


def _validate_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    try:
        _VisionSlipPayloadModel.model_validate(payload)
    except ValidationError as exc:
        return [{'path': '.'.join(str(part) for part in err.get('loc', [])) or '$', 'message': err.get('msg', 'validation error')} for err in exc.errors()]

    errors: list[dict[str, str]] = []
    if payload['sportsbook'] not in _SPORTSBOOK_ENUM:
        errors.append({'path': 'sportsbook', 'message': f'value "{payload["sportsbook"]}" not in enum'})
    if payload['screenshot_state'] not in _SCREENSHOT_STATE_ENUM:
        errors.append({'path': 'screenshot_state', 'message': f'value "{payload["screenshot_state"]}" not in enum'})
    if payload['confidence'] not in _CONFIDENCE_ENUM:
        errors.append({'path': 'confidence', 'message': f'value "{payload["confidence"]}" not in enum'})
    for idx, leg in enumerate(payload['parsed_legs']):
        if leg['market'] not in _MARKET_ENUM:
            errors.append({'path': f'parsed_legs.{idx}.market', 'message': f'value "{leg["market"]}" not in enum'})
        if leg['selection'] not in _SELECTION_ENUM:
            errors.append({'path': f'parsed_legs.{idx}.selection', 'message': f'value "{leg["selection"]}" not in enum'})
    return errors


def _extract_output_text(body: dict[str, Any]) -> str:
    diagnostics = _extract_response_diagnostics(body)
    return str(diagnostics.get('combined_output_text', '')).strip()


def _extract_response_diagnostics(body: dict[str, Any]) -> dict[str, Any]:
    direct_output_text = body.get('output_text')
    text_chunks: list[str] = []
    if isinstance(direct_output_text, str) and direct_output_text.strip():
        text_chunks.append(direct_output_text.strip())

    refusals: list[str] = []
    output = body.get('output', [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get('content', [])
            if isinstance(content, list):
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text_value = content_item.get('text')
                    if isinstance(text_value, str) and text_value.strip():
                        text_chunks.append(text_value.strip())
                    refusal = content_item.get('refusal')
                    if isinstance(refusal, str) and refusal.strip():
                        refusals.append(refusal.strip())

    combined_output_text = '\n'.join(text_chunks).strip()
    return {
        'response_status': body.get('status'),
        'response_finish_reason': body.get('finish_reason') or body.get('stop_reason'),
        'response_incomplete_details': body.get('incomplete_details'),
        'response_refusal': body.get('refusal'),
        'response_output': body.get('output'),
        'response_output_text': body.get('output_text'),
        'response_refusal_messages': refusals,
        'has_refusal': bool(body.get('refusal')) or bool(refusals),
        'has_any_text': bool(combined_output_text),
        'combined_output_text': combined_output_text,
    }


def _sanitize_response_object(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == 'image_url' and isinstance(item, str) and item.startswith('data:image'):
                sanitized[key] = f'<redacted_data_url length={len(item)}>'
                continue
            sanitized[key] = _sanitize_response_object(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_response_object(item) for item in value]
    if isinstance(value, str) and len(value) > 6000:
        return value[:6000] + '...<truncated>'
    return value


def _attempt_tolerant_json_parse(raw_text: str) -> dict[str, Any] | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_legs = _extract_leg_rows(payload)
    normalized: dict[str, Any] = {
        'sportsbook': _normalize_sportsbook(payload.get('sportsbook')),
        'screenshot_state': _normalize_screenshot_state(payload.get('screenshot_state')),
        'confidence': _normalize_confidence(payload.get('confidence')),
        'warnings': _normalize_warnings(payload.get('warnings')),
        'parsed_legs': [],
    }
    for leg in source_legs:
        if isinstance(leg, dict):
            prop_parts = _parse_prop_text(leg.get('prop'))
            normalized['parsed_legs'].append(
                {
                    'player_name': str(leg.get('player_name') or leg.get('name') or ''),
                    'market': _normalize_market(leg.get('market') or prop_parts.get('market')),
                    'line': _normalize_line(leg.get('line') or prop_parts.get('line')),
                    'selection': _normalize_selection(leg.get('selection') or prop_parts.get('selection')),
                    'raw_text': str(leg.get('raw_text') or leg.get('prop') or ''),
                }
            )
    return normalized


def _extract_leg_rows(payload: dict[str, Any]) -> list[Any]:
    for key in _LEG_LIST_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    return []


def _parse_prop_text(value: Any) -> dict[str, Any]:
    text = str(value or '').strip()
    if not text:
        return {}
    match = re.match(r'^(over|under)\s+([0-9]+(?:\.[0-9]+)?)\s+(.+)$', text, flags=re.IGNORECASE)
    if not match:
        return {}
    selection, line, market = match.groups()
    return {'selection': selection.lower(), 'line': line, 'market': market}


def _normalize_market(value: Any) -> str:
    raw_market = str(value or '').strip().lower()
    registry_normalized = normalize_market_with_registry(raw_market)
    if registry_normalized:
        return registry_normalized
    return _MARKET_VARIANTS.get(raw_market, raw_market)


def _normalize_selection(value: Any) -> str:
    text = str(value or '').strip().lower()
    return 'over' if text == 'more' else 'under' if text == 'less' else text


def _normalize_line(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    return value


def _normalize_sportsbook(value: Any) -> str:
    text = str(value or '').strip().lower()
    if text in _SPORTSBOOK_ENUM:
        return text
    if text in _SPORTSBOOK_VARIANTS:
        return _SPORTSBOOK_VARIANTS[text]
    return 'unknown'


def _normalize_screenshot_state(value: Any) -> str:
    text = str(value or '').strip().lower()
    return text if text in _SCREENSHOT_STATE_ENUM else _SCREENSHOT_STATE_VARIANTS.get(text, 'unknown')


def _normalize_confidence(value: Any) -> str:
    text = str(value or '').strip().lower()
    if text in _CONFIDENCE_ENUM:
        return text
    if text in _CONFIDENCE_VARIANTS:
        return _CONFIDENCE_VARIANTS[text]
    if 'high' in text:
        return 'high'
    if 'med' in text:
        return 'medium'
    return 'low'


def _normalize_warnings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _merge_schema_diagnostics_into_artifacts(debug_artifacts: dict[str, str], diagnostics: dict[str, Any]) -> None:
    debug_artifacts['primary_failure_category'] = str(diagnostics.get('primary_failure_category', 'vision_schema_error'))
    if diagnostics.get('provider_response_kind'):
        debug_artifacts['provider_response_kind'] = str(diagnostics['provider_response_kind'])
    if diagnostics.get('response_status') is not None:
        debug_artifacts['response_status'] = str(diagnostics['response_status'])
    if diagnostics.get('response_finish_reason') is not None:
        debug_artifacts['response_finish_reason'] = str(diagnostics['response_finish_reason'])
    if diagnostics.get('schema_error_path'):
        debug_artifacts['schema_error_path'] = str(diagnostics['schema_error_path'])
    if diagnostics.get('schema_error_message'):
        debug_artifacts['schema_error_message'] = str(diagnostics['schema_error_message'])
    if diagnostics.get('raw_primary_output_excerpt'):
        debug_artifacts['raw_primary_output_excerpt'] = str(diagnostics['raw_primary_output_excerpt'])
    if diagnostics.get('schema_repair_applied') is not None:
        debug_artifacts['schema_repair_applied'] = str(diagnostics['schema_repair_applied'])


def _excerpt(text: str, max_len: int = 300) -> str:
    return ' '.join(text.split())[:max_len]


def classify_failure(exc: Exception) -> str:
    text = str(exc).lower()
    if 'vision_preprocessing_error' in text:
        return 'vision_preprocessing_error'
    if 'vision_schema_error' in text or 'decode' in text or 'json' in text or 'structured output' in text:
        return 'vision_schema_error'
    if 'api_key' in text or 'required' in text or '401' in text:
        return 'vision_provider_error'
    if isinstance(exc, httpx.HTTPStatusError):
        return 'vision_provider_error'
    if 'image' in text or 'too large' in text or 'unsupported' in text:
        return 'vision_preprocessing_error'
    return 'vision_provider_error'


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
