from ppchem.decks.deck_resolution import build_reaction_lookup, resolve_deck_records
from ppchem.decks.deck_schema import DeckRecord
from ppchem.models.reaction_schema import ReactionRecord


def _record(reaction_id: str) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        source="base",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles="CCO>>CC=O",
        reactants_smiles=["CCO"],
        products_smiles=["CC=O"],
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_build_reaction_lookup_indexes_by_reaction_id() -> None:
    lookup = build_reaction_lookup([_record("base_1"), _record("base_2")])

    assert sorted(lookup.keys()) == ["base_1", "base_2"]


def test_resolve_deck_records_preserves_order_for_existing_ids() -> None:
    deck = DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_2", "base_1"])
    lookup = build_reaction_lookup([_record("base_1"), _record("base_2")])

    resolution = resolve_deck_records(deck, lookup)

    assert [record.reaction_id for record in resolution.records] == ["base_2", "base_1"]
    assert resolution.missing_reaction_ids == []


def test_resolve_deck_records_reports_missing_ids() -> None:
    deck = DeckRecord(deck_id="starter", name="Starter", reaction_ids=["base_1", "missing_1", "missing_2"])
    lookup = build_reaction_lookup([_record("base_1")])

    resolution = resolve_deck_records(deck, lookup)

    assert [record.reaction_id for record in resolution.records] == ["base_1"]
    assert resolution.missing_reaction_ids == ["missing_1", "missing_2"]
