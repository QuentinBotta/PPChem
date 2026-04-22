from pathlib import Path

from ppchem.decks.deck_io import read_deck_records, write_deck_records
from ppchem.decks.deck_schema import DeckRecord


def test_write_and_read_deck_records(tmp_path: Path) -> None:
    out_path = tmp_path / "decks.json"
    decks = [
        DeckRecord(
            deck_id="starter",
            name="Starter",
            description="Small test deck",
            reaction_ids=["base_1", "base_2"],
        )
    ]

    write_deck_records(decks, out_path)
    loaded = read_deck_records(out_path)

    assert len(loaded) == 1
    assert loaded[0].deck_id == "starter"
    assert loaded[0].reaction_ids == ["base_1", "base_2"]


def test_deck_record_rejects_missing_required_fields() -> None:
    try:
        DeckRecord.from_dict({"deck_id": "starter", "reaction_ids": ["base_1"]})
    except ValueError:
        return

    raise AssertionError("Expected missing deck fields to raise ValueError")
