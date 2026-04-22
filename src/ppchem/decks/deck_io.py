from __future__ import annotations

import json
from pathlib import Path

from .deck_schema import DeckRecord


def write_deck_records(decks: list[DeckRecord], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [deck.to_dict() for deck in decks]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_deck_records(path: str | Path) -> list[DeckRecord]:
    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return [DeckRecord.from_dict(item) for item in payload]
