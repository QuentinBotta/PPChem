from ppchem.app.reaction_browser import (
    BrowserFilters,
    choose_selected_record,
    build_browser_page_signature,
    compute_browser_reactant_slider_state,
    compute_browser_pagination,
    filter_reactions,
    paginate_reactions,
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


def test_build_browser_page_signature_tracks_filter_and_page_size_changes() -> None:
    signature = build_browser_page_signature(
        BrowserFilters(search_text=" Oxidation ", max_reactants=2, source="user"),
        page_size=50,
    )

    assert signature == ("oxidation", 2, "user", 50)


def test_compute_browser_pagination_clamps_page_index_and_range() -> None:
    pagination = compute_browser_pagination(total_results=2347, page_size=500, requested_page_index=99)

    assert pagination.page_index == 4
    assert pagination.total_pages == 5
    assert pagination.start_index == 2000
    assert pagination.end_index == 2347


def test_compute_browser_pagination_handles_empty_results() -> None:
    pagination = compute_browser_pagination(total_results=0, page_size=100, requested_page_index=3)

    assert pagination.page_index == 0
    assert pagination.total_pages == 1
    assert pagination.start_index == 0
    assert pagination.end_index == 0


def test_paginate_reactions_returns_only_visible_page_records() -> None:
    records = [
        _record(f"base_{index}", "CCO>>CC=O", ["CCO"], ["CC=O"])
        for index in range(1, 11)
    ]
    pagination = compute_browser_pagination(total_results=len(records), page_size=3, requested_page_index=2)

    visible = paginate_reactions(records, pagination)

    assert [record.reaction_id for record in visible] == ["base_7", "base_8", "base_9"]


def test_compute_browser_reactant_slider_state_uses_dataset_max_and_clamps_value() -> None:
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("base_2", "CCN.CCO.CCCl.CBr>>CC=N", ["CCN", "CCO", "CCCl", "CBr"], ["CC=N"]),
    ]

    state = compute_browser_reactant_slider_state(records, requested_value=10)

    assert state.max_value == 4
    assert state.current_value == 4


def test_compute_browser_reactant_slider_state_uses_safe_fallback_for_empty_records() -> None:
    state = compute_browser_reactant_slider_state([], requested_value=None)

    assert state.max_value == 3
    assert state.current_value == 3
