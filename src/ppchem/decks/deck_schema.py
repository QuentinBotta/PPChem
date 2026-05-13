"""Schema for persistent reaction decks.

Decks store only deck metadata plus ordered `reaction_id` references. They do
not duplicate full reaction payloads, which keeps decks small and lets edited
reactions show up everywhere that references the same stable identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DeckRecord:
    """User-visible deck definition persisted as JSON."""

    deck_id: str
    name: str
    description: str = ""
    reaction_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DeckRecord":
        """Load one deck from JSON and validate its reaction reference list."""
        required = ["deck_id", "name", "reaction_ids"]
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        reaction_ids = value["reaction_ids"]
        if not isinstance(reaction_ids, list) or any(not isinstance(item, str) or not item for item in reaction_ids):
            raise ValueError("reaction_ids must be a list of non-empty strings")

        description = value.get("description", "")
        if description is None:
            description = ""

        return cls(
            deck_id=str(value["deck_id"]),
            name=str(value["name"]),
            description=str(description),
            reaction_ids=list(reaction_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the deck back to plain JSON data."""
        return asdict(self)
