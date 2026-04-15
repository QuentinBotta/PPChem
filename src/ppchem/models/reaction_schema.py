from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ReactionRecord:
    """Internal reaction schema used by the app data layer.

    Fields that are pedagogical (display_name, reaction_class, difficulty, hint)
    are intentionally nullable for imported data.
    """

    reaction_id: str
    source: str
    created_by: str
    created_at: str
    reaction_smiles: str
    reactants_smiles: list[str]
    products_smiles: list[str]
    display_name: str | None = None
    reaction_class: str | None = None
    tags: list[str] = field(default_factory=list)
    difficulty: int | None = None
    hint: str | None = None
    notes: str | None = None
    quality: dict[str, Any] = field(default_factory=lambda: {"is_validated": False, "validation_messages": []})
    provenance: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(
        default_factory=lambda: {
            "conditions": None,
            "catalyst": None,
            "mechanism": None,
            "references": [],
        }
    )

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReactionRecord":
        required = [
            "reaction_id",
            "source",
            "created_by",
            "created_at",
            "reaction_smiles",
            "reactants_smiles",
            "products_smiles",
            "quality",
            "provenance",
        ]
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        if not self.reaction_smiles:
            raise ValueError("reaction_smiles cannot be empty")
        if ">>" not in self.reaction_smiles:
            raise ValueError("reaction_smiles must contain '>>'")
        return asdict(self)
