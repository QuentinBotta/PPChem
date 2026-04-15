from ppchem.models.reaction_schema import ReactionRecord


def test_reaction_record_round_trip() -> None:
    record = ReactionRecord(
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

    payload = record.to_dict()
    rebuilt = ReactionRecord.from_dict(payload)

    assert rebuilt.reaction_id == "base_1"
    assert rebuilt.display_name is None
    assert rebuilt.tags == []


def test_reaction_smiles_requires_separator() -> None:
    record = ReactionRecord(
        reaction_id="base_1",
        source="base",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles="INVALID",
        reactants_smiles=[],
        products_smiles=[],
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "x", "dataset_record_id": "1", "import_version": "0.1"},
    )

    try:
        record.to_dict()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert ">>" in str(exc)
