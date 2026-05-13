"""Resolve deck references against loaded reaction records.

Decks intentionally point to `reaction_id` values instead of list positions so
they keep working after filtering, reordering, or editing records. This module
turns those stable references back into full `ReactionRecord` objects.
"""

from __future__ import annotations

from dataclasses import dataclass

from ppchem.decks.deck_schema import DeckRecord
from ppchem.models.reaction_schema import ReactionRecord


@dataclass(frozen=True)
class DeckResolution:
    """Result of resolving one deck against the currently loaded reaction store."""

    deck: DeckRecord
    records: list[ReactionRecord]
    missing_reaction_ids: list[str]


def build_reaction_lookup(records: list[ReactionRecord]) -> dict[str, ReactionRecord]:
    """Index reactions by `reaction_id` for fast deck lookup."""
    return {record.reaction_id: record for record in records}


def resolve_deck_records(deck: DeckRecord, reaction_lookup: dict[str, ReactionRecord]) -> DeckResolution:
    """Resolve stored deck IDs while preserving order and reporting missing IDs."""
    resolved_records: list[ReactionRecord] = []
    missing_reaction_ids: list[str] = []

    for reaction_id in deck.reaction_ids:
        record = reaction_lookup.get(reaction_id)
        if record is None:
            missing_reaction_ids.append(reaction_id)
            continue
        resolved_records.append(record)

    return DeckResolution(deck=deck, records=resolved_records, missing_reaction_ids=missing_reaction_ids)
