"""Helpers that mutate persisted deck files without changing reaction data.

These functions centralize deck edits so the Streamlit UI does not have to
manually reason about ID generation, duplicate entries, or JSON persistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ppchem.decks.deck_io import read_deck_records, write_deck_records
from ppchem.decks.deck_schema import DeckRecord


@dataclass(frozen=True)
class DeckUpdateResult:
    deck: DeckRecord
    created_new_deck: bool
    added_reaction: bool


@dataclass(frozen=True)
class DeckRemovalResult:
    deck: DeckRecord
    removed_reaction: bool


@dataclass(frozen=True)
class DeckBulkRemovalResult:
    affected_decks: list[DeckRecord]
    removed_reaction: bool


@dataclass(frozen=True)
class DeckDeletionResult:
    deck: DeckRecord
    deleted_deck: bool


def make_deck_id_from_name(name: str) -> str:
    """Create a filesystem-friendly deck identifier from a visible name."""
    normalized = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return normalized or "deck"


def choose_unique_deck_id(base_deck_id: str, existing_deck_ids: set[str]) -> str:
    """Add a numeric suffix until the deck ID is unique within the store."""
    if base_deck_id not in existing_deck_ids:
        return base_deck_id

    suffix = 2
    while True:
        candidate = f"{base_deck_id}_{suffix}"
        if candidate not in existing_deck_ids:
            return candidate
        suffix += 1


def add_reaction_to_decks_file(
    path: str | Path,
    *,
    reaction_id: str,
    selected_deck_id: str = "",
    new_deck_name: str = "",
) -> DeckUpdateResult:
    """Add one reaction ID to an existing deck or a newly created deck.

    Reaction membership is keyed by `reaction_id`, not by where the reaction
    currently appears in a filtered list or paginated browser table.
    """
    decks_path = Path(path)
    decks = read_deck_records(decks_path) if decks_path.exists() else []

    normalized_new_deck_name = new_deck_name.strip()
    chosen_deck_id = selected_deck_id.strip()

    if normalized_new_deck_name:
        existing_deck_ids = {deck.deck_id for deck in decks}
        base_deck_id = make_deck_id_from_name(normalized_new_deck_name)
        new_deck_id = choose_unique_deck_id(base_deck_id, existing_deck_ids)
        target_deck = DeckRecord(deck_id=new_deck_id, name=normalized_new_deck_name, description="", reaction_ids=[])
        decks.append(target_deck)
        created_new_deck = True
    elif chosen_deck_id:
        target_deck = next((deck for deck in decks if deck.deck_id == chosen_deck_id), None)
        if target_deck is None:
            raise ValueError(f"Could not find deck: {chosen_deck_id}")
        created_new_deck = False
    else:
        raise ValueError("Choose an existing deck or provide a new deck name")

    if reaction_id in target_deck.reaction_ids:
        updated_deck = target_deck
        added_reaction = False
    else:
        # Preserve existing order and append the new reference once. Decks act
        # like ordered study lists, so we avoid re-sorting here.
        updated_deck = DeckRecord(
            deck_id=target_deck.deck_id,
            name=target_deck.name,
            description=target_deck.description,
            reaction_ids=[*target_deck.reaction_ids, reaction_id],
        )
        added_reaction = True

    updated_decks = [updated_deck if deck.deck_id == target_deck.deck_id else deck for deck in decks]
    write_deck_records(updated_decks, decks_path)

    return DeckUpdateResult(deck=updated_deck, created_new_deck=created_new_deck, added_reaction=added_reaction)


def remove_reaction_from_decks_file(
    path: str | Path,
    *,
    reaction_id: str,
    selected_deck_id: str,
) -> DeckRemovalResult:
    """Remove one reaction ID from one selected deck, leaving other decks alone."""
    decks_path = Path(path)
    decks = read_deck_records(decks_path) if decks_path.exists() else []

    chosen_deck_id = selected_deck_id.strip()
    if not chosen_deck_id:
        raise ValueError("Choose a deck to remove from")

    target_deck = next((deck for deck in decks if deck.deck_id == chosen_deck_id), None)
    if target_deck is None:
        raise ValueError(f"Could not find deck: {chosen_deck_id}")

    if reaction_id in target_deck.reaction_ids:
        updated_reaction_ids = [item for item in target_deck.reaction_ids if item != reaction_id]
        removed_reaction = True
    else:
        updated_reaction_ids = list(target_deck.reaction_ids)
        removed_reaction = False

    updated_deck = DeckRecord(
        deck_id=target_deck.deck_id,
        name=target_deck.name,
        description=target_deck.description,
        reaction_ids=updated_reaction_ids,
    )

    updated_decks = [updated_deck if deck.deck_id == target_deck.deck_id else deck for deck in decks]
    write_deck_records(updated_decks, decks_path)

    return DeckRemovalResult(deck=updated_deck, removed_reaction=removed_reaction)


def find_decks_referencing_reaction(decks: list[DeckRecord], reaction_id: str) -> list[DeckRecord]:
    """Return every deck that currently contains the given reaction ID."""
    return [deck for deck in decks if reaction_id in deck.reaction_ids]


def delete_deck_from_file(
    path: str | Path,
    *,
    selected_deck_id: str,
) -> DeckDeletionResult:
    """Delete a whole deck definition by deck ID."""
    decks_path = Path(path)
    decks = read_deck_records(decks_path) if decks_path.exists() else []

    chosen_deck_id = selected_deck_id.strip()
    if not chosen_deck_id:
        raise ValueError("Choose a deck to delete")

    target_deck = next((deck for deck in decks if deck.deck_id == chosen_deck_id), None)
    if target_deck is None:
        raise ValueError(f"Could not find deck: {chosen_deck_id}")

    updated_decks = [deck for deck in decks if deck.deck_id != chosen_deck_id]
    write_deck_records(updated_decks, decks_path)

    return DeckDeletionResult(deck=target_deck, deleted_deck=True)


def remove_reaction_from_all_decks_file(
    path: str | Path,
    *,
    reaction_id: str,
) -> DeckBulkRemovalResult:
    """Remove a reaction ID from every deck that references it.

    This is used when deleting a user reaction so no deck keeps a dangling
    reference to an ID that no longer exists locally.
    """
    decks_path = Path(path)
    decks = read_deck_records(decks_path) if decks_path.exists() else []

    affected_decks = find_decks_referencing_reaction(decks, reaction_id)
    if not affected_decks:
        return DeckBulkRemovalResult(affected_decks=[], removed_reaction=False)

    updated_decks: list[DeckRecord] = []
    updated_affected_decks: list[DeckRecord] = []
    for deck in decks:
        if reaction_id not in deck.reaction_ids:
            updated_decks.append(deck)
            continue

        updated_deck = DeckRecord(
            deck_id=deck.deck_id,
            name=deck.name,
            description=deck.description,
            reaction_ids=[item for item in deck.reaction_ids if item != reaction_id],
        )
        updated_decks.append(updated_deck)
        updated_affected_decks.append(updated_deck)

    write_deck_records(updated_decks, decks_path)
    return DeckBulkRemovalResult(affected_decks=updated_affected_decks, removed_reaction=True)
