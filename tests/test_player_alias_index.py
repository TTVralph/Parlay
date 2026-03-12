from app.services.player_alias_index import (
    normalize_player_name,
    player_aliases_from_name,
    resolve_snapshot_player,
)


def test_normalize_player_name_handles_punctuation_spacing_and_suffixes() -> None:
    assert normalize_player_name(' LeBron   James, Jr. ') == 'lebron james'
    assert normalize_player_name('D\'Angelo   Russell III') == 'd angelo russell'


def test_aliases_include_initial_last_and_first_name() -> None:
    aliases = player_aliases_from_name('LeBron James Jr.')

    assert 'lebron james' in aliases
    assert 'l james' in aliases
    assert 'lebron' in aliases


def test_alias_match_succeeds_when_direct_and_normalized_do_not() -> None:
    entries = [
        {
            'player_id': '23',
            'display_name': 'LeBron James Jr.',
            'stats': {'PTS': 30},
        }
    ]

    match = resolve_snapshot_player(
        player_entries=entries,
        player_id='999',
        player_name='L. James',
    )

    assert match.entry == entries[0]
    assert match.strategy == 'alias_match'


def test_fuzzy_match_respects_threshold() -> None:
    entries = [{'player_id': '23', 'display_name': 'LeBron James', 'stats': {}}]

    strong = resolve_snapshot_player(
        player_entries=entries,
        player_id=None,
        player_name='Lebron Jamez',
        enable_fuzzy=True,
        fuzzy_threshold=0.9,
    )
    strict = resolve_snapshot_player(
        player_entries=entries,
        player_id=None,
        player_name='Lebron Jamez',
        enable_fuzzy=True,
        fuzzy_threshold=0.99,
    )

    assert strong.entry == entries[0]
    assert strong.strategy == 'fuzzy_match'
    assert strict.entry is None
    assert strict.strategy == 'match_failed'


def test_direct_match_is_preferred_when_player_id_is_present() -> None:
    entries = [{'player_id': '23', 'display_name': 'LeBron James', 'stats': {'PTS': 30}}]

    match = resolve_snapshot_player(
        player_entries=entries,
        player_id='23',
        player_name='L. James',
    )

    assert match.entry == entries[0]
    assert match.strategy == 'direct_match'
