from ppchem.app.reaction_browser import (
    BrowserFilters,
    choose_selected_record,
    filter_reactions,
    reaction_label,
    reaction_search_text,
    records_to_table,
)
from ppchem.models.reaction_schema import ReactionRecord


def _record(
    reaction_id: str,
    reaction_smiles: str,
    reactants: list[str],
    products: list[str],
    *,
    display_name: str | None = None,
    tags: list[str] | None = None,
) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        source="user" if reaction_id.startswith("user_") else "base",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles=reaction_smiles,
        reactants_smiles=reactants,
        products_smiles=products,
        display_name=display_name,
        tags=tags or [],
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_reaction_label_falls_back_to_reaction_id() -> None:
    record = _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"])

    assert reaction_label(record) == "base_1"


def test_filter_reactions_searches_existing_structural_fields() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("base_2", "CCN.CCO>>CC=N", ["CCN", "CCO"], ["CC=N"]),
    ]

    filtered = filter_reactions(records, BrowserFilters(search_text="ccn", max_reactants=1))

    assert filtered == []

    filtered = filter_reactions(records, BrowserFilters(search_text="ccn", max_reactants=2))

    assert [record.reaction_id for record in filtered] == ["base_2"]


def test_filter_reactions_searches_display_name() -> None:
    records = [
        _record("user_1", "CCO>>CC=O", ["CCO"], ["CC=O"], display_name="Alcohol oxidation"),
        _record("user_2", "CCN>>CC=N", ["CCN"], ["CC=N"], display_name="Imine formation"),
    ]

    filtered = filter_reactions(records, BrowserFilters(search_text="oxidation"))

    assert [record.reaction_id for record in filtered] == ["user_1"]


def test_filter_reactions_searches_tags() -> None:
    records = [
        _record("user_1", "CCO>>CC=O", ["CCO"], ["CC=O"], tags=["practice", "oxidation"]),
        _record("user_2", "CCN>>CC=N", ["CCN"], ["CC=N"], tags=["imine"]),
    ]

    filtered = filter_reactions(records, BrowserFilters(search_text="practice"))

    assert [record.reaction_id for record in filtered] == ["user_1"]


def test_filter_reactions_can_limit_to_user_source() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("user_1", "CCN>>CC=N", ["CCN"], ["CC=N"]),
    ]

    filtered = filter_reactions(records, BrowserFilters(source="user"))

    assert [record.reaction_id for record in filtered] == ["user_1"]


def test_filter_reactions_combines_source_and_search_filters() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"], display_name="Oxidation"),
        _record("user_1", "CCN>>CC=N", ["CCN"], ["CC=N"], display_name="Oxidation notes"),
        _record("user_2", "CCC>>CC=C", ["CCC"], ["CC=C"], display_name="Elimination"),
    ]

    filtered = filter_reactions(records, BrowserFilters(search_text="oxidation", source="user"))

    assert [record.reaction_id for record in filtered] == ["user_1"]


def test_reaction_search_text_includes_human_and_technical_fields() -> None:
    record = _record(
        "user_7",
        "CCO>>CC=O",
        ["CCO"],
        ["CC=O"],
        display_name="Alcohol oxidation",
        tags=["practice", "chapter 3"],
    )

    search_text = reaction_search_text(record)

    assert "alcohol oxidation" in search_text
    assert "practice chapter 3" in search_text
    assert "user_7" in search_text
    assert "cco>>cc=o" in search_text


def test_choose_selected_record_uses_selected_row_when_available() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("user_1", "CCN>>CC=N", ["CCN"], ["CC=N"]),
    ]

    selected = choose_selected_record(records, selected_rows=[1], previous_reaction_id="base_1")

    assert selected is not None
    assert selected.reaction_id == "user_1"


def test_choose_selected_record_falls_back_to_previous_selection() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("user_1", "CCN>>CC=N", ["CCN"], ["CC=N"]),
    ]

    selected = choose_selected_record(records, selected_rows=[], previous_reaction_id="user_1")

    assert selected is not None
    assert selected.reaction_id == "user_1"


def test_records_to_table_uses_reliable_counts() -> None:
    table = records_to_table([_record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"])])

    assert table.iloc[0]["reaction_id"] == "base_1"
    assert table.iloc[0]["source"] == "base"
    assert table.iloc[0]["reactants"] == 1
    assert table.iloc[0]["products"] == 1
