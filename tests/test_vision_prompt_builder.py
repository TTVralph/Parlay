from __future__ import annotations

from app.services.vision_parser import _JSON_SCHEMA
from app.services.vision_prompt_builder import build_vision_prompts


def test_strategy_selection_bet365() -> None:
    strategy = build_vision_prompts('bet365')
    assert strategy.parser_strategy_used == 'bet365'
    assert 'Strategy: bet365 layout.' in strategy.layout_notes


def test_strategy_selection_unknown_fallback() -> None:
    strategy = build_vision_prompts('my_custom_book')
    assert strategy.parser_strategy_used == 'unknown'
    assert 'unknown generic sportsbook layout' in strategy.layout_notes


def test_prompt_builder_injects_sportsbook_specific_instructions() -> None:
    strategy = build_vision_prompts('fanduel')
    assert 'Strategy: fanduel layout.' in strategy.system_prompt
    assert 'navigation tabs' in strategy.system_prompt
    assert 'Parser strategy: fanduel.' in strategy.user_prompt


def test_normalized_schema_remains_unchanged() -> None:
    assert _JSON_SCHEMA['required'] == ['sportsbook', 'screenshot_state', 'confidence', 'warnings', 'parsed_legs']
    assert _JSON_SCHEMA['properties']['parsed_legs']['items']['required'] == [
        'player_name', 'market', 'line', 'selection', 'raw_text'
    ]
