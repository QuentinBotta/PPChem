from pathlib import Path

from ppchem.decks.deck_io import read_deck_records
from ppchem.decks.deck_schema import DeckRecord
from ppchem.decks.deck_transfer import (
    DECK_COLLISION_CHOICE_MERGE,
    DECK_COLLISION_CHOICE_SEPARATE,
    DUPLICATE_DECISION_IMPORT_AS_NEW,
    DUPLICATE_DECISION_USE_EXISTING,
    analyze_deck_package_import,
    build_imported_deck_name,
    choose_unique_deck_name,
    export_deck_package_json,
    finalize_deck_package_import_into_store,
    parse_deck_package_json,
)
from ppchem.models.reaction_io import read_reaction_records, write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


def _record(reaction_id: str, reaction_smiles: str = "CCO>>CC=O") -> ReactionRecord:
    left, right = reaction_smiles.split(">>", maxsplit=1)
    return ReactionRecord(
        reaction_id=reaction_id,
        source="base" if reaction_id.startswith("base_") else "user",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles=reaction_smiles,
        reactants_smiles=[token for token in left.split(".") if token],
        products_smiles=[token for token in right.split(".") if token],
        display_name=f"Reaction {reaction_id}",
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_export_deck_package_json_bundles_deck_and_reaction_payloads() -> None:
    deck = DeckRecord(deck_id="starter", name="Starter", description="Example", reaction_ids=["base_1", "user_2"])

    payload = export_deck_package_json(
        deck,
        reaction_lookup={
            "base_1": _record("base_1", "CCO>>CC=O"),
            "user_2": _record("user_2", "CCN>>CC=N"),
        },
    )

    assert '"format_version": "portable_deck_package_v1"' in payload
    assert '"reaction_refs": [' in payload
    assert '"package_reaction_id": "base_1"' in payload
    assert '"reaction_smiles": "CCN>>CC=N"' in payload


def test_parse_deck_package_json_reads_package_shape() -> None:
    package = parse_deck_package_json(
        """{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "Starter",
    "description": "Example",
    "reaction_refs": ["base_1", "base_1", "user_2"]
  },
  "reactions": [
    {
      "package_reaction_id": "base_1",
      "reaction": {
        "reaction_id": "base_1",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "display_name": "Reaction base_1",
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_1", "import_version": "0.1"}
      }
    },
    {
      "package_reaction_id": "user_2",
      "reaction": {
        "reaction_id": "user_2",
        "source": "user",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCN>>CC=N",
        "reactants_smiles": ["CCN"],
        "products_smiles": ["CC=N"],
        "display_name": "Reaction user_2",
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "user_2", "import_version": "0.1"}
      }
    }
  ]
}"""
    )

    assert package.deck_id == "starter"
    assert package.reaction_refs == ["base_1", "user_2"]
    assert [entry.package_reaction_id for entry in package.reactions] == ["base_1", "user_2"]


def test_build_imported_deck_name_adds_clear_imported_suffix() -> None:
    assert build_imported_deck_name("BA3", {"Starter", "BA3"}) == "BA3 (Imported)"
    assert build_imported_deck_name("BA3", {"BA3", "BA3 (Imported)"}) == "BA3 (Imported) 2"


def test_analyze_deck_package_import_detects_exact_smiles_duplicates() -> None:
    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "Starter",
    "description": "",
    "reaction_refs": ["pkg_1", "pkg_2"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    },
    {
      "package_reaction_id": "pkg_2",
      "reaction": {
        "reaction_id": "base_10",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCN>>CC=N",
        "reactants_smiles": ["CCN"],
        "products_smiles": ["CC=N"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_10", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[_record("base_1", "CCO>>CC=O"), _record("user_1", "CCC>>CC=C")],
    )

    assert analysis.no_conflict_reaction_ids == ["pkg_2"]
    assert len(analysis.duplicate_candidates) == 1
    assert analysis.duplicate_candidates[0].package_reaction_id == "pkg_1"
    assert analysis.duplicate_candidates[0].existing_local_reaction.reaction_id == "base_1"


def test_analyze_deck_package_import_reports_deck_collisions_by_name_and_id() -> None:
    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "Starter",
    "description": "",
    "reaction_refs": ["pkg_1"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[],
        existing_decks=[
            DeckRecord(deck_id="starter", name="Different visible name", reaction_ids=[]),
            DeckRecord(deck_id="other", name="Starter", reaction_ids=[]),
        ],
    )

    assert [candidate.deck_id for candidate in analysis.deck_collision_candidates] == ["starter", "other"]
    assert analysis.deck_collision_candidates[0].collision_reasons == ["same deck_id"]
    assert analysis.deck_collision_candidates[1].collision_reasons == ["same visible name"]


def test_finalize_deck_package_import_into_store_creates_new_reactions_and_deck(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("user_1", "CCC>>CC=C")], user_path)

    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "Starter",
    "description": "Imported deck",
    "reaction_refs": ["pkg_1", "pkg_2"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    },
    {
      "package_reaction_id": "pkg_2",
      "reaction": {
        "reaction_id": "base_10",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCN>>CC=N",
        "reactants_smiles": ["CCN"],
        "products_smiles": ["CC=N"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_10", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[_record("base_1", "CCO>>CC=O"), _record("user_1", "CCC>>CC=C")],
    )

    result = finalize_deck_package_import_into_store(
        analysis=analysis,
        duplicate_decisions={"pkg_1": DUPLICATE_DECISION_USE_EXISTING},
        local_records=[_record("base_1", "CCO>>CC=O"), _record("user_1", "CCC>>CC=C")],
        user_path=user_path,
        decks_path=decks_path,
    )
    stored_decks = read_deck_records(decks_path)
    stored_user_reactions = read_reaction_records(user_path)

    assert result.final_deck.reaction_ids == ["base_1", "user_2"]
    assert result.used_existing_reaction_ids == ["base_1"]
    assert [record.reaction_id for record in result.created_reactions] == ["user_2"]
    assert [deck.deck_id for deck in stored_decks] == ["starter"]
    assert [record.reaction_id for record in stored_user_reactions] == ["user_1", "user_2"]


def test_finalize_deck_package_import_into_store_can_import_duplicate_as_new(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("user_1", "CCO>>CC=O")], user_path)

    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "Starter",
    "description": "",
    "reaction_refs": ["pkg_1"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[_record("user_1", "CCO>>CC=O")],
    )

    result = finalize_deck_package_import_into_store(
        analysis=analysis,
        duplicate_decisions={"pkg_1": DUPLICATE_DECISION_IMPORT_AS_NEW},
        local_records=[_record("user_1", "CCO>>CC=O")],
        user_path=user_path,
        decks_path=decks_path,
    )

    assert [record.reaction_id for record in result.created_reactions] == ["user_2"]
    assert result.final_deck.reaction_ids == ["user_2"]


def test_finalize_deck_package_import_can_merge_into_existing_deck(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([_record("user_1", "CCC>>CC=C")], user_path)
    from ppchem.decks.deck_io import write_deck_records

    write_deck_records(
        [DeckRecord(deck_id="starter_local", name="BA3", description="", reaction_ids=["base_1"])],
        decks_path,
    )

    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "BA3",
    "description": "Imported deck",
    "reaction_refs": ["pkg_1", "pkg_2"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    },
    {
      "package_reaction_id": "pkg_2",
      "reaction": {
        "reaction_id": "base_10",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCN>>CC=N",
        "reactants_smiles": ["CCN"],
        "products_smiles": ["CC=N"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_10", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[_record("base_1", "CCO>>CC=O"), _record("user_1", "CCC>>CC=C")],
        existing_decks=[DeckRecord(deck_id="starter_local", name="BA3", description="", reaction_ids=["base_1"])],
    )

    result = finalize_deck_package_import_into_store(
        analysis=analysis,
        duplicate_decisions={"pkg_1": DUPLICATE_DECISION_USE_EXISTING},
        local_records=[_record("base_1", "CCO>>CC=O"), _record("user_1", "CCC>>CC=C")],
        user_path=user_path,
        decks_path=decks_path,
        deck_collision_choice=DECK_COLLISION_CHOICE_MERGE,
        merge_target_deck_id="starter_local",
    )
    stored_decks = read_deck_records(decks_path)

    assert result.merged_into_existing_deck is True
    assert result.deck_reaction_ids_added_count == 1
    assert result.final_deck.deck_id == "starter_local"
    assert result.final_deck.reaction_ids == ["base_1", "user_2"]
    assert stored_decks[0].reaction_ids == ["base_1", "user_2"]


def test_finalize_deck_package_import_creates_distinct_visible_name_when_separate(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([], user_path)
    from ppchem.decks.deck_io import write_deck_records

    write_deck_records(
        [
            DeckRecord(deck_id="starter", name="BA3", description="", reaction_ids=[]),
            DeckRecord(deck_id="other", name="BA3 (Imported)", description="", reaction_ids=[]),
        ],
        decks_path,
    )

    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "BA3",
    "description": "",
    "reaction_refs": ["pkg_1"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[],
        existing_decks=[
            DeckRecord(deck_id="starter", name="BA3", description="", reaction_ids=[]),
            DeckRecord(deck_id="other", name="BA3 (Imported)", description="", reaction_ids=[]),
        ],
    )

    result = finalize_deck_package_import_into_store(
        analysis=analysis,
        duplicate_decisions={},
        local_records=[],
        user_path=user_path,
        decks_path=decks_path,
        deck_collision_choice=DECK_COLLISION_CHOICE_SEPARATE,
    )

    assert result.merged_into_existing_deck is False
    assert result.deck_reaction_ids_added_count == 1
    assert result.final_deck_id == "starter_2"
    assert result.final_deck_name == "BA3 (Imported) 2"


def test_finalize_deck_package_import_merge_reports_noop_when_all_reactions_already_present(tmp_path: Path) -> None:
    user_path = tmp_path / "reactions.user.json"
    decks_path = tmp_path / "decks.json"
    write_reaction_records([], user_path)
    from ppchem.decks.deck_io import write_deck_records

    write_deck_records(
        [DeckRecord(deck_id="ba3_local", name="BA3", description="", reaction_ids=["base_1", "base_2"])],
        decks_path,
    )

    analysis = analyze_deck_package_import(
        raw_json="""{
  "format_version": "portable_deck_package_v1",
  "deck": {
    "deck_id": "starter",
    "name": "BA3",
    "description": "",
    "reaction_refs": ["pkg_1", "pkg_2"]
  },
  "reactions": [
    {
      "package_reaction_id": "pkg_1",
      "reaction": {
        "reaction_id": "base_9",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCO>>CC=O",
        "reactants_smiles": ["CCO"],
        "products_smiles": ["CC=O"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_9", "import_version": "0.1"}
      }
    },
    {
      "package_reaction_id": "pkg_2",
      "reaction": {
        "reaction_id": "base_10",
        "source": "base",
        "created_by": "test",
        "created_at": "2026-04-14T00:00:00Z",
        "reaction_smiles": "CCN>>CC=N",
        "reactants_smiles": ["CCN"],
        "products_smiles": ["CC=N"],
        "quality": {"is_validated": false, "validation_messages": []},
        "provenance": {"dataset": "test", "dataset_record_id": "base_10", "import_version": "0.1"}
      }
    }
  ]
}""",
        local_records=[_record("base_1", "CCO>>CC=O"), _record("base_2", "CCN>>CC=N")],
        existing_decks=[DeckRecord(deck_id="ba3_local", name="BA3", description="", reaction_ids=["base_1", "base_2"])],
    )

    result = finalize_deck_package_import_into_store(
        analysis=analysis,
        duplicate_decisions={
            "pkg_1": DUPLICATE_DECISION_USE_EXISTING,
            "pkg_2": DUPLICATE_DECISION_USE_EXISTING,
        },
        local_records=[_record("base_1", "CCO>>CC=O"), _record("base_2", "CCN>>CC=N")],
        user_path=user_path,
        decks_path=decks_path,
        deck_collision_choice=DECK_COLLISION_CHOICE_MERGE,
        merge_target_deck_id="ba3_local",
    )
    stored_decks = read_deck_records(decks_path)

    assert result.merged_into_existing_deck is True
    assert result.deck_reaction_ids_added_count == 0
    assert result.final_deck.reaction_ids == ["base_1", "base_2"]
    assert stored_decks[0].reaction_ids == ["base_1", "base_2"]
