from __future__ import annotations

import json
from pathlib import Path

from .reaction_schema import ReactionRecord


def write_reaction_records(records: list[ReactionRecord], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.to_dict() for record in records]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_reaction_records(path: str | Path) -> list[ReactionRecord]:
    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return [ReactionRecord.from_dict(item) for item in payload]
