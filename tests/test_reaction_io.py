from pathlib import Path

from ppchem.models.reaction_io import read_reaction_records, write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


def test_write_and_read_records(tmp_path: Path) -> None:
    out_path = tmp_path / "reactions.json"
    records = [
        ReactionRecord(
            reaction_id="base_1",
            source="base",
            created_by="test",
            created_at="2026-04-14T00:00:00Z",
            reaction_smiles="CCO>>CC=O",
            reactants_smiles=["CCO"],
            products_smiles=["CC=O"],
            quality={"is_validated": True, "validation_messages": []},
            provenance={"dataset": "x", "dataset_record_id": "1", "import_version": "0.1"},
        )
    ]

    write_reaction_records(records, out_path)
    loaded = read_reaction_records(out_path)

    assert len(loaded) == 1
    assert loaded[0].reaction_smiles == "CCO>>CC=O"
