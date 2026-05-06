from pathlib import Path

from ppchem.app.reaction_sources import (
    append_user_reaction,
    build_reaction_smiles_from_visual_inputs,
    build_imported_user_reaction_record,
    build_updated_user_reaction_record,
    build_user_reaction_record,
    delete_user_reaction_with_deck_cleanup,
    delete_user_reaction_from_store,
    find_reaction_by_id,
    load_app_reactions,
    load_optional_reactions,
    normalize_user_tags,
    next_user_reaction_id,
    split_reaction_smiles,
    update_user_reaction_in_store,
    validate_unique_reaction_ids,
)
from ppchem.decks.deck_io import read_deck_records, write_deck_records
from ppchem.decks.deck_resolution import build_reaction_lookup, resolve_deck_records
from ppchem.decks.deck_schema import DeckRecord
from ppchem.models.reaction_io import write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


def _record(reaction_id: str) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        source="base" if reaction_id.startswith("base_") else "user",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles="CCO>>CC=O",
        reactants_smiles=["CCO"],
        products_smiles=["CC=O"],
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_load_optional_reactions_returns_empty_list_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    assert load_optional_reactions(missing_path) == []


def test_load_app_reactions_merges_base_and_user_records(tmp_path: Path) -> None:
    base_path = tmp_path / "reactions.base.json"
    user_path = tmp_path / "reactions.user.json"
    write_reaction_records([_record("base_1"), _record("base_2")], base_path)
    write_reaction_records([_record("user_1")], user_path)

    loaded = load_app_reactions(base_path=base_path, user_path=user_path)

    assert [record.reaction_id for record in loaded] == ["base_1", "base_2", "user_1"]


def test_load_app_reactions_handles_missing_user_store_as_empty(tmp_path: Path) -> None:
    base_path = tmp_path / "reactions.base.json"
    write_reaction_records([_record("base_1")], base_path)

    loaded = load_app_reactions(base_path=base_path, user_path=tmp_path / "reactions.user.json")

    assert [record.reaction_id for record in loaded] == ["base_1"]


def test_load_app_reactions_rejects_duplicate_reaction_id_collision(tmp_path: Path) -> None:
    base_path = tmp_path / "reactions.base.json"
    user_path = tmp_path / "reactions.user.json"
    write_reaction_records([_record("base_1"), _record("base_2")], base_path)
    colliding_user_record = _record("base_2")
    colliding_user_record.source = "user"
    write_reaction_records([colliding_user_record], user_path)

    try:
        load_app_reactions(base_path=base_path, user_path=user_path)
    except ValueError as exc:
        message = str(exc)
        assert "Duplicate reaction_id values found while loading merged reactions" in message
        assert "base_2" in message
        return

    raise AssertionError("Expected duplicate merged reaction_id collision to raise ValueError")


def test_validate_unique_reaction_ids_accepts_unique_records() -> None:
    validate_unique_reaction_ids([_record("base_1"), _record("user_1"), _record("user_2")])


def test_next_user_reaction_id_uses_user_namespace_safely() -> None:
    records = [_record("base_1"), _record("user_1"), _record("user_3")]

    assert next_user_reaction_id(records) == "user_2"


def test_split_reaction_smiles_rejects_missing_separator() -> None:
    try:
        split_reaction_smiles("CCO>CC=O")
    except ValueError:
        return

    raise AssertionError("Expected invalid reaction SMILES to raise ValueError")


def test_build_reaction_smiles_from_visual_inputs_combines_both_sides() -> None:
    reaction_smiles = build_reaction_smiles_from_visual_inputs(
        reactants_smiles="CCO.O",
        products_smiles="CC=O",
    )

    assert reaction_smiles == "CCO.O>>CC=O"


def test_build_reaction_smiles_from_visual_inputs_rejects_missing_side() -> None:
    try:
        build_reaction_smiles_from_visual_inputs(
            reactants_smiles="",
            products_smiles="CC=O",
        )
    except ValueError as exc:
        assert "reactant" in str(exc).lower()
        return

    raise AssertionError("Expected missing visual reactants to raise ValueError")


def test_build_user_reaction_record_creates_user_metadata() -> None:
    record = build_user_reaction_record(
        reaction_smiles="CCO>>CC=O",
        existing_records=[_record("base_1"), _record("user_1")],
        display_name="Oxidation example",
        raw_tags="practice, aldehyde, practice",
        created_by="test_ui",
    )

    assert record.reaction_id == "user_2"
    assert record.source == "user"
    assert record.created_by == "test_ui"
    assert record.display_name == "Oxidation example"
    assert record.tags == ["practice", "aldehyde"]
    assert record.reactants_smiles == ["CCO"]
    assert record.products_smiles == ["CC=O"]


def test_append_user_reaction_writes_to_user_store(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"

    new_record = append_user_reaction(
        user_path=user_path,
        reaction_smiles="CCO>>CC=O",
        existing_records=[_record("base_1")],
        display_name="My saved reaction",
        raw_tags="tag one, tag two",
        created_by="test_ui",
    )
    loaded = load_optional_reactions(user_path)

    assert new_record.reaction_id == "user_1"
    assert new_record.display_name == "My saved reaction"
    assert new_record.tags == ["tag one", "tag two"]
    assert [record.reaction_id for record in loaded] == ["user_1"]


def test_build_imported_user_reaction_record_assigns_new_user_identity() -> None:
    source = _record("base_7")
    source.display_name = "Imported"
    source.tags = ["shared", "deck"]

    imported = build_imported_user_reaction_record(
        source,
        existing_records=[_record("base_1"), _record("user_1")],
        package_reaction_id="pkg_rxn_1",
    )

    assert imported.reaction_id == "user_2"
    assert imported.source == "user"
    assert imported.created_by == "deck_package_import"
    assert imported.display_name == "Imported"
    assert imported.tags == ["shared", "deck"]
    assert imported.provenance["package_reaction_id"] == "pkg_rxn_1"
    assert imported.provenance["package_original_reaction_id"] == "base_7"


def test_normalize_user_tags_trims_drops_empty_and_deduplicates() -> None:
    assert normalize_user_tags(" alpha, beta , , alpha, gamma ") == ["alpha", "beta", "gamma"]


def test_find_reaction_by_id_does_not_depend_on_position() -> None:
    records = [_record("user_4"), _record("user_1"), _record("user_9")]

    found = find_reaction_by_id(records, "user_1")

    assert found is not None
    assert found.reaction_id == "user_1"


def test_build_updated_user_reaction_record_preserves_identity_fields() -> None:
    existing = _record("user_3")

    updated = build_updated_user_reaction_record(
        existing,
        reaction_smiles="CCN>>CC=N",
        display_name="Updated name",
        raw_tags="study, updated",
    )

    assert updated.reaction_id == "user_3"
    assert updated.source == "user"
    assert updated.created_at == existing.created_at
    assert updated.created_by == existing.created_by
    assert updated.display_name == "Updated name"
    assert updated.tags == ["study", "updated"]


def test_build_updated_user_reaction_record_rejects_base_reaction() -> None:
    existing = _record("base_3")

    try:
        build_updated_user_reaction_record(
            existing,
            reaction_smiles="CCN>>CC=N",
            display_name="Updated name",
            raw_tags="study, updated",
        )
    except ValueError:
        return

    raise AssertionError("Expected base reaction editing to be rejected")


def test_update_user_reaction_in_store_replaces_by_reaction_id_not_order(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    records = [_record("user_8"), _record("user_2"), _record("user_5")]
    write_reaction_records(records, user_path)

    updated = build_updated_user_reaction_record(
        records[1],
        reaction_smiles="CCN>>CC=N",
        display_name="Edited reaction",
        raw_tags="edited",
    )
    update_user_reaction_in_store(user_path=user_path, reaction_id="user_2", updated_record=updated)
    loaded = load_optional_reactions(user_path)

    assert [record.reaction_id for record in loaded] == ["user_8", "user_2", "user_5"]
    assert loaded[1].reaction_id == "user_2"
    assert loaded[1].display_name == "Edited reaction"
    assert loaded[1].reaction_smiles == "CCN>>CC=N"
    assert loaded[1].reactants_smiles == ["CCN"]
    assert loaded[1].products_smiles == ["CC=N"]
    assert loaded[1].created_at == records[1].created_at
    assert loaded[1].created_by == records[1].created_by


def test_update_user_reaction_in_store_rejects_reaction_id_change(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    original = _record("user_2")
    write_reaction_records([original], user_path)

    updated = build_updated_user_reaction_record(
        original,
        reaction_smiles="CCN>>CC=N",
        display_name="Edited reaction",
        raw_tags="edited",
    )
    updated.reaction_id = "user_9"
    try:
        update_user_reaction_in_store(user_path=user_path, reaction_id="user_2", updated_record=updated)
    except ValueError:
        return

    raise AssertionError("Expected reaction_id change to be rejected")


def test_delete_user_reaction_from_store_uses_reaction_id_not_order(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    write_reaction_records([_record("user_8"), _record("user_2"), _record("user_5")], user_path)

    removed = delete_user_reaction_from_store(user_path=user_path, reaction_id="user_2")
    loaded = load_optional_reactions(user_path)

    assert removed is True
    assert [record.reaction_id for record in loaded] == ["user_8", "user_5"]


def test_delete_user_reaction_with_deck_cleanup_deletes_unreferenced_user_reaction(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("user_2"), _record("user_5")], user_path)
    write_deck_records([DeckRecord(deck_id="study", name="Study", reaction_ids=["base_1"])], decks_path)

    result = delete_user_reaction_with_deck_cleanup(
        user_path=user_path,
        decks_path=decks_path,
        reaction_id="user_2",
    )

    assert result.removed_from_user_store is True
    assert result.affected_deck_ids == []
    assert [record.reaction_id for record in load_optional_reactions(user_path)] == ["user_5"]
    assert read_deck_records(decks_path)[0].reaction_ids == ["base_1"]


def test_delete_user_reaction_with_deck_cleanup_removes_deck_references(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("user_2"), _record("user_5")], user_path)
    write_deck_records(
        [
            DeckRecord(deck_id="study", name="Study", reaction_ids=["user_2", "base_1"]),
            DeckRecord(deck_id="review", name="Review", reaction_ids=["user_2"]),
        ],
        decks_path,
    )

    result = delete_user_reaction_with_deck_cleanup(
        user_path=user_path,
        decks_path=decks_path,
        reaction_id="user_2",
    )
    decks = read_deck_records(decks_path)

    assert result.removed_from_user_store is True
    assert result.affected_deck_ids == ["study", "review"]
    assert result.affected_deck_names == ["Study", "Review"]
    assert [record.reaction_id for record in load_optional_reactions(user_path)] == ["user_5"]
    assert decks[0].reaction_ids == ["base_1"]
    assert decks[1].reaction_ids == []


def test_delete_user_reaction_with_deck_cleanup_rejects_base_reactions(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("base_2")], user_path)
    write_deck_records([], decks_path)

    try:
        delete_user_reaction_with_deck_cleanup(
            user_path=user_path,
            decks_path=decks_path,
            reaction_id="base_2",
        )
    except ValueError:
        return

    raise AssertionError("Expected base reaction deletion to be rejected")


def test_deck_references_remain_valid_after_non_id_user_reaction_update(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    original = _record("user_2")
    write_reaction_records([original], user_path)

    updated = build_updated_user_reaction_record(
        original,
        reaction_smiles="CCN>>CC=N",
        display_name="Edited reaction",
        raw_tags="edited",
    )
    update_user_reaction_in_store(user_path=user_path, reaction_id="user_2", updated_record=updated)

    deck = DeckRecord(deck_id="study", name="Study", reaction_ids=["user_2"])
    lookup = build_reaction_lookup(load_optional_reactions(user_path))
    resolution = resolve_deck_records(deck, lookup)

    assert [record.reaction_id for record in resolution.records] == ["user_2"]
    assert resolution.records[0].display_name == "Edited reaction"
    assert resolution.missing_reaction_ids == []
