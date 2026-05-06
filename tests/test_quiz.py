import random

from ppchem.app.quiz import (
    build_quiz_source_key,
    QuizPoolStatus,
    QuizFilters,
    ScheduledQuizSelection,
    QuizStats,
    choose_scheduled_quiz_reaction,
    QuizSourcePool,
    choose_random_reaction,
    choose_quiz_source_pool,
    filter_quiz_records,
    format_quiz_answer,
    format_quiz_prompt,
    recent_history_limit,
    reset_quiz_session_state,
    review_grade_label,
    summarize_quiz_pool,
    sync_quiz_session_source,
    update_relearning_reaction_ids,
    update_recent_history,
)
from ppchem.app.quiz_progress import QuizProgressRecord
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
    stats = QuizStats(again=2, hard=1, good=3, easy=4)

    assert stats.answered == 10


def test_review_grade_label_formats_all_supported_grades() -> None:
    assert review_grade_label("again") == "Again"
    assert review_grade_label("hard") == "Hard"
    assert review_grade_label("good") == "Good"
    assert review_grade_label("easy") == "Easy"


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


def test_build_quiz_source_key_changes_when_source_changes() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"])]

    deck_a = build_quiz_source_key(records, source_label="Deck A", allow_study_ahead=False)
    deck_b = build_quiz_source_key(records, source_label="Deck B", allow_study_ahead=False)
    study_ahead = build_quiz_source_key(records, source_label="Deck A", allow_study_ahead=True)

    assert deck_a != deck_b
    assert deck_a != study_ahead


def test_sync_quiz_session_source_clears_stale_completion_state() -> None:
    session_state = {
        "quiz_source_key": "deck_a",
        "quiz_count_again": 2,
        "quiz_count_hard": 1,
        "quiz_count_good": 0,
        "quiz_count_easy": 0,
        "quiz_revealed": True,
        "quiz_last_result": "Marked Again",
        "quiz_recent_reaction_ids": ["base_1"],
        "quiz_relearning_reaction_ids": ["base_1"],
        "quiz_reaction_id": None,
        "quiz_selection_mode": "complete",
    }

    changed = sync_quiz_session_source(session_state, "deck_b")

    assert changed is True
    assert session_state["quiz_source_key"] == "deck_b"
    assert session_state["quiz_count_again"] == 0
    assert session_state["quiz_recent_reaction_ids"] == []
    assert session_state["quiz_relearning_reaction_ids"] == []
    assert session_state["quiz_reaction_id"] is None
    assert session_state["quiz_selection_mode"] is None


def test_reset_quiz_session_state_clears_stale_quiz_state() -> None:
    session_state = {
        "quiz_count_again": 1,
        "quiz_count_hard": 2,
        "quiz_count_good": 3,
        "quiz_count_easy": 4,
        "quiz_revealed": True,
        "quiz_last_result": "Marked Easy",
        "quiz_recent_reaction_ids": ["base_1", "base_2"],
        "quiz_relearning_reaction_ids": ["base_1"],
        "quiz_reaction_id": "base_2",
        "quiz_selection_mode": "due",
    }

    reset_quiz_session_state(session_state)

    assert session_state["quiz_count_again"] == 0
    assert session_state["quiz_count_hard"] == 0
    assert session_state["quiz_count_good"] == 0
    assert session_state["quiz_count_easy"] == 0
    assert session_state["quiz_revealed"] is False
    assert session_state["quiz_last_result"] is None
    assert session_state["quiz_recent_reaction_ids"] == []
    assert session_state["quiz_relearning_reaction_ids"] == []
    assert session_state["quiz_reaction_id"] is None
    assert session_state["quiz_selection_mode"] is None


def test_choose_scheduled_quiz_reaction_prefers_due_records() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
        _record("base_3", ["CCC"], ["CC=C"]),
    ]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-04-28T10:00:00Z"),
        "base_2": QuizProgressRecord(reaction_id="base_2", due_at="2026-04-30T10:00:00Z"),
    }

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id=progress_by_id,
        allow_study_ahead=False,
        relearning_reaction_ids=[],
        now_at="2026-04-29T10:00:00Z",
        rng=random.Random(0),
    )

    assert isinstance(selection, ScheduledQuizSelection)
    assert selection.selection_mode == "due"
    assert selection.record.reaction_id == "base_1"


def test_choose_scheduled_quiz_reaction_uses_unseen_when_nothing_is_due() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
    ]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-05-01T10:00:00Z"),
    }

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id=progress_by_id,
        allow_study_ahead=False,
        relearning_reaction_ids=[],
        now_at="2026-04-29T10:00:00Z",
        rng=random.Random(0),
    )

    assert selection.selection_mode == "unseen"
    assert selection.record.reaction_id == "base_2"


def test_choose_scheduled_quiz_reaction_falls_back_when_no_due_or_unseen_records_exist() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
    ]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-05-01T10:00:00Z"),
        "base_2": QuizProgressRecord(reaction_id="base_2", due_at="2026-05-02T10:00:00Z"),
    }

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id=progress_by_id,
        allow_study_ahead=False,
        relearning_reaction_ids=[],
        now_at="2026-04-29T10:00:00Z",
        previous_reaction_id="base_1",
        rng=random.Random(0),
    )

    assert selection.selection_mode == "complete"
    assert selection.record is None


def test_choose_scheduled_quiz_reaction_can_study_ahead_from_reviewed_not_due_cards() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
    ]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-05-01T10:00:00Z"),
        "base_2": QuizProgressRecord(reaction_id="base_2", due_at="2026-05-02T10:00:00Z"),
    }

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id=progress_by_id,
        allow_study_ahead=True,
        relearning_reaction_ids=[],
        now_at="2026-04-29T10:00:00Z",
        previous_reaction_id="base_1",
        rng=random.Random(0),
    )

    assert selection.selection_mode == "study_ahead"
    assert selection.record is not None
    assert selection.record.reaction_id == "base_2"


def test_switching_to_new_deck_allows_fresh_due_or_new_selection() -> None:
    deck_a_records = [_record("base_1", ["CCO"], ["CC=O"])]
    deck_b_records = [_record("base_2", ["CCN"], ["CC=N"])]
    session_state = {
        "quiz_source_key": build_quiz_source_key(deck_a_records, source_label="Deck A", allow_study_ahead=False),
        "quiz_count_again": 1,
        "quiz_count_hard": 0,
        "quiz_count_good": 0,
        "quiz_count_easy": 0,
        "quiz_revealed": False,
        "quiz_last_result": None,
        "quiz_recent_reaction_ids": ["base_1"],
        "quiz_relearning_reaction_ids": ["base_1"],
        "quiz_reaction_id": None,
        "quiz_selection_mode": "complete",
    }
    progress_by_id = {}

    changed = sync_quiz_session_source(
        session_state,
        build_quiz_source_key(deck_b_records, source_label="Deck B", allow_study_ahead=False),
    )
    selection = choose_scheduled_quiz_reaction(
        deck_b_records,
        progress_by_id=progress_by_id,
        allow_study_ahead=False,
        relearning_reaction_ids=session_state["quiz_relearning_reaction_ids"],
        recent_reaction_ids=session_state["quiz_recent_reaction_ids"],
        rng=random.Random(0),
    )

    assert changed is True
    assert session_state["quiz_selection_mode"] is None
    assert session_state["quiz_recent_reaction_ids"] == []
    assert session_state["quiz_relearning_reaction_ids"] == []
    assert selection.selection_mode == "unseen"
    assert selection.record is not None
    assert selection.record.reaction_id == "base_2"


def test_again_cards_reappear_in_same_session() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"]), _record("base_2", ["CCN"], ["CC=N"])]
    relearning_ids = update_relearning_reaction_ids([], reaction_id="base_1", keep_in_relearning=True)

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id={},
        allow_study_ahead=False,
        relearning_reaction_ids=relearning_ids,
        recent_reaction_ids=[],
        rng=random.Random(0),
    )

    assert selection.selection_mode == "relearning"
    assert selection.record is not None
    assert selection.record.reaction_id == "base_1"


def test_all_again_cards_do_not_finish_session_after_one_pass() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"]), _record("base_2", ["CCN"], ["CC=N"])]
    relearning_ids = update_relearning_reaction_ids([], reaction_id="base_1", keep_in_relearning=True)
    relearning_ids = update_relearning_reaction_ids(relearning_ids, reaction_id="base_2", keep_in_relearning=True)

    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id={},
        allow_study_ahead=False,
        relearning_reaction_ids=relearning_ids,
        recent_reaction_ids=["base_1"],
        rng=random.Random(0),
    )

    assert selection.selection_mode == "relearning"
    assert selection.record is not None
    assert selection.record.reaction_id == "base_2"


def test_hard_good_easy_do_not_stay_in_relearning_loop() -> None:
    relearning_ids = update_relearning_reaction_ids([], reaction_id="base_1", keep_in_relearning=True)

    assert update_relearning_reaction_ids(relearning_ids, reaction_id="base_1", keep_in_relearning=False) == []


def test_session_completes_only_when_due_new_and_relearning_are_empty() -> None:
    records = [_record("base_1", ["CCO"], ["CC=O"])]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-05-01T10:00:00Z"),
    }

    status = summarize_quiz_pool(
        records,
        progress_by_id=progress_by_id,
        relearning_reaction_ids=["base_1"],
        now_at="2026-04-29T10:00:00Z",
    )
    selection = choose_scheduled_quiz_reaction(
        records,
        progress_by_id=progress_by_id,
        allow_study_ahead=False,
        relearning_reaction_ids=["base_1"],
        now_at="2026-04-29T10:00:00Z",
        rng=random.Random(0),
    )

    assert status.eligible_count == 1
    assert status.relearning_count == 1
    assert selection.selection_mode == "relearning"


def test_summarize_quiz_pool_reports_due_unseen_and_not_due_counts() -> None:
    records = [
        _record("base_1", ["CCO"], ["CC=O"]),
        _record("base_2", ["CCN"], ["CC=N"]),
        _record("base_3", ["CCC"], ["CC=C"]),
    ]
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", due_at="2026-04-28T10:00:00Z"),
        "base_2": QuizProgressRecord(reaction_id="base_2", due_at="2026-05-01T10:00:00Z"),
    }

    status = summarize_quiz_pool(records, progress_by_id=progress_by_id, now_at="2026-04-29T10:00:00Z")

    assert isinstance(status, QuizPoolStatus)
    assert status.due_count == 1
    assert status.unseen_count == 1
    assert status.reviewed_not_due_count == 1
    assert status.eligible_count == 2
