from pathlib import Path

from ppchem.decks.deck_io import read_deck_records, write_deck_records
from ppchem.decks.deck_mutations import (
    add_reaction_to_decks_file,
    choose_unique_deck_id,
    make_deck_id_from_name,
    remove_reaction_from_decks_file,
)
from ppchem.decks.deck_schema import DeckRecord


def test_make_deck_id_from_name_normalizes_text() -> None:
    assert make_deck_id_from_name(" My Starter Deck! ") == "my_starter_deck"


def test_choose_unique_deck_id_adds_numeric_suffix() -> None:
    assert choose_unique_deck_id("starter", {"starter", "starter_2"}) == "starter_3"


def test_add_reaction_to_existing_deck_avoids_duplicates(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1"])],
        decks_path,
    )

    result = add_reaction_to_decks_file(decks_path, reaction_id="base_1", selected_deck_id="starter")
    decks = read_deck_records(decks_path)

    assert result.created_new_deck is False
    assert result.added_reaction is False
    assert decks[0].reaction_ids == ["base_1"]


def test_add_reaction_to_existing_deck_appends_new_id(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1"])],
        decks_path,
    )

    result = add_reaction_to_decks_file(decks_path, reaction_id="base_2", selected_deck_id="starter")
    decks = read_deck_records(decks_path)

    assert result.created_new_deck is False
    assert result.added_reaction is True
    assert decks[0].reaction_ids == ["base_1", "base_2"]


def test_add_reaction_can_create_new_deck_from_name(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"

    result = add_reaction_to_decks_file(decks_path, reaction_id="base_3", new_deck_name="Starter Set")
    decks = read_deck_records(decks_path)

    assert result.created_new_deck is True
    assert result.deck.deck_id == "starter_set"
    assert decks[0].reaction_ids == ["base_3"]


def test_add_reaction_creates_unique_deck_id_on_collision(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter_set", name="Starter Set", reaction_ids=["base_1"])],
        decks_path,
    )

    result = add_reaction_to_decks_file(decks_path, reaction_id="base_2", new_deck_name="Starter Set")
    decks = read_deck_records(decks_path)

    assert result.created_new_deck is True
    assert result.deck.deck_id == "starter_set_2"
    assert [deck.deck_id for deck in decks] == ["starter_set", "starter_set_2"]


def test_new_deck_name_takes_precedence_over_existing_deck_selection(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1"])],
        decks_path,
    )

    result = add_reaction_to_decks_file(
        decks_path,
        reaction_id="base_2",
        selected_deck_id="starter",
        new_deck_name="Fresh Deck",
    )
    decks = read_deck_records(decks_path)

    assert result.created_new_deck is True
    assert result.deck.deck_id == "fresh_deck"
    assert [deck.deck_id for deck in decks] == ["starter", "fresh_deck"]


def test_add_reaction_requires_existing_or_new_deck_choice(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"

    try:
        add_reaction_to_decks_file(decks_path, reaction_id="base_3")
    except ValueError:
        return

    raise AssertionError("Expected missing deck choice to raise ValueError")


def test_remove_reaction_from_existing_deck_updates_file(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1", "base_2"])],
        decks_path,
    )

    result = remove_reaction_from_decks_file(decks_path, reaction_id="base_1", selected_deck_id="starter")
    decks = read_deck_records(decks_path)

    assert result.removed_reaction is True
    assert result.deck.reaction_ids == ["base_2"]
    assert decks[0].reaction_ids == ["base_2"]


def test_remove_reaction_from_deck_requires_selected_deck(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"

    try:
        remove_reaction_from_decks_file(decks_path, reaction_id="base_1", selected_deck_id="")
    except ValueError:
        return

    raise AssertionError("Expected missing deck selection to raise ValueError")


def test_remove_reaction_from_deck_handles_missing_reaction_id_gracefully(tmp_path: Path) -> None:
    decks_path = tmp_path / "decks.json"
    write_deck_records(
        [DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1"])],
        decks_path,
    )

    result = remove_reaction_from_decks_file(decks_path, reaction_id="base_9", selected_deck_id="starter")
    decks = read_deck_records(decks_path)

    assert result.removed_reaction is False
    assert result.deck.reaction_ids == ["base_1"]
    assert decks[0].reaction_ids == ["base_1"]
