import random

from ppchem.app.quiz import (
    QuizFilters,
    QuizStats,
    QuizSourcePool,
    choose_random_reaction,
    choose_quiz_source_pool,
    filter_quiz_records,
    format_quiz_answer,
    format_quiz_prompt,
    recent_history_limit,
    update_recent_history,
)
from ppchem.models.reaction_schema import ReactionRecord


def _record(reaction_id: str, reactants: list[str], products: list[str]) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        source="base",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles=f"{'.'.join(reactants)}>>{'.'.join(products)}",
        reactants_smiles=reactants,
        products_smiles=products,
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_choose_random_reaction_avoids_previous_when_possible() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"]), _record("base_2", ["CCN"], ["CC=N"])]

    chosen = choose_random_reaction(records, previous_reaction_id="base_1", rng=random.Random(0))

    assert chosen.reaction_id == "base_2"


def test_choose_random_reaction_handles_single_record() -> None:
    record = _record("base_1", ["CCO"], ["CC=O"])

    assert choose_random_reaction([record], previous_reaction_id="base_1") == record


def test_choose_random_reaction_avoids_recent_history_when_possible() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
        _record("base_3", ["CCC"], ["CC=C"]),
    ]

    chosen = choose_random_reaction(records, recent_reaction_ids=["base_1", "base_2"], rng=random.Random(0))

    assert chosen.reaction_id == "base_3"


def test_choose_random_reaction_falls_back_gracefully_when_pool_is_small() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"]), _record("base_2", ["CCN"], ["CC=N"])]

    chosen = choose_random_reaction(
        records,
        previous_reaction_id="base_2",
        recent_reaction_ids=["base_1", "base_2"],
        rng=random.Random(0),
    )

    assert chosen.reaction_id == "base_1"


def test_choose_random_reaction_rejects_empty_list() -> None:
    try:
        choose_random_reaction([])
    except ValueError:
        return

    raise AssertionError("Expected choose_random_reaction to reject an empty list")


def test_quiz_prompt_and_answer_use_existing_structural_data() -> None:
    record = _record("base_1", ["CCO", "O"], ["CC=O"])

    assert format_quiz_prompt(record) == ["CCO", "O"]
    assert format_quiz_answer(record) == ["CC=O"]


def test_quiz_stats_counts_answered_cards() -> None:
    stats = QuizStats(correct=2, incorrect=3)

    assert stats.answered == 5


def test_filter_quiz_records_applies_quiz_only_filters() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN", "O"], ["CC=N"]),
        _record("base_3", ["CCC"], ["CC=C", "O"]),
    ]

    filtered = filter_quiz_records(records, QuizFilters(max_reactants=1, require_single_product=True))

    assert [record.reaction_id for record in filtered] == ["base_1"]


def test_recent_history_limit_stays_short() -> None:
    assert recent_history_limit(1) == 1
    assert recent_history_limit(3) == 2
    assert recent_history_limit(10) == 5


def test_update_recent_history_keeps_most_recent_unique_ids() -> None:
    history = update_recent_history(["base_1", "base_2", "base_3"], "base_2", max_length=3)

    assert history == ["base_1", "base_3", "base_2"]


def test_choose_quiz_source_pool_uses_selected_deck_records() -> None:
    all_records = [_record("base_1", ["CCO"], ["CC=O"]), _record("base_2", ["CCN"], ["CC=N"])]
    deck_records = [all_records[1]]

    source_pool = choose_quiz_source_pool(all_records, deck_records=deck_records, deck_name="Starter Deck")

    assert isinstance(source_pool, QuizSourcePool)
    assert source_pool.label == "Starter Deck"
    assert [record.reaction_id for record in source_pool.records] == ["base_2"]


def test_choose_quiz_source_pool_can_intersect_deck_with_browser_subset() -> None:
    all_records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
        _record("base_3", ["CCC"], ["CC=C"]),
    ]
    deck_records = [all_records[0], all_records[1]]
    browser_subset_records = [all_records[1], all_records[2]]

    source_pool = choose_quiz_source_pool(
        all_records,
        deck_records=deck_records,
        deck_name="Starter Deck",
        browser_subset_records=browser_subset_records,
        use_browser_subset=True,
    )

    assert source_pool.label == "Deck: Starter Deck + Browser subset"
    assert [record.reaction_id for record in source_pool.records] == ["base_2"]
