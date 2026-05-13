"""JSON persistence helpers for reaction stores.

The app never reads raw CSV directly. Importers first normalize external data
into `ReactionRecord` objects, then the rest of the codebase consumes those
stable JSON records.
"""

from __future__ import annotations

import json
from pathlib import Path

from .reaction_schema import ReactionRecord


def write_reaction_records(records: list[ReactionRecord], path: str | Path) -> None:
    """Write reaction records as pretty JSON, creating parent folders if needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.to_dict() for record in records]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_reaction_records(path: str | Path) -> list[ReactionRecord]:
    """Load reaction records from a JSON file into typed dataclass instances."""
    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return [ReactionRecord.from_dict(item) for item in payload]
