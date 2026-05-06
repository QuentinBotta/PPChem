from pathlib import Path

from ppchem.app.quiz_progress import (
    QuizProgressRecord,
    ReactionStudyStatus,
    compute_next_interval_days,
    compute_quiz_progress_totals,
    format_review_grade_label,
    is_due,
    load_quiz_progress,
    record_quiz_result_in_store,
    summarize_reaction_study_status,
    update_quiz_progress,
    write_quiz_progress,
)


def test_load_quiz_progress_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert load_quiz_progress(tmp_path / "quiz_progress.json") == {}


def test_write_and_load_quiz_progress_round_trip(tmp_path: Path) -> None:
    progress_path = tmp_path / "quiz_progress.json"
    progress_by_id = {
        "base_1": QuizProgressRecord(
            reaction_id="base_1",
            times_seen=3,
            count_again=1,
            count_hard=0,
            count_good=2,
            count_easy=0,
            last_seen_at="2026-04-29T10:00:00Z",
        )
    }

    write_quiz_progress(progress_by_id, progress_path)
    loaded = load_quiz_progress(progress_path)

    assert sorted(loaded.keys()) == ["base_1"]
    assert loaded["base_1"].times_seen == 3
    assert loaded["base_1"].count_again == 1
    assert loaded["base_1"].count_good == 2
    assert loaded["base_1"].last_grade is None
    assert loaded["base_1"].last_seen_at == "2026-04-29T10:00:00Z"
    assert loaded["base_1"].last_reviewed_at == "2026-04-29T10:00:00Z"
    assert loaded["base_1"].due_at is None
    assert loaded["base_1"].interval_days is None


def test_update_quiz_progress_accumulates_by_reaction_id() -> None:
    progress_by_id = {}

    first = update_quiz_progress(
        progress_by_id,
        reaction_id="base_7",
        review_grade="good",
        seen_at="2026-04-29T10:00:00Z",
    )
    second = update_quiz_progress(
        progress_by_id,
        reaction_id="base_7",
        review_grade="again",
        seen_at="2026-04-29T10:05:00Z",
    )

    assert first.times_seen == 1
    assert second.times_seen == 2
    assert second.count_again == 1
    assert second.count_good == 1
    assert second.count_hard == 0
    assert second.count_easy == 0
    assert second.last_grade == "again"
    assert second.last_seen_at == "2026-04-29T10:05:00Z"
    assert second.last_reviewed_at == "2026-04-29T10:05:00Z"
    assert second.interval_days == 5 / (24 * 60)
    assert second.due_at == "2026-04-29T10:10:00Z"


def test_record_quiz_result_in_store_persists_updates(tmp_path: Path) -> None:
    progress_path = tmp_path / "quiz_progress.json"

    record_quiz_result_in_store(
        progress_path,
        reaction_id="user_2",
        review_grade="hard",
        seen_at="2026-04-29T10:00:00Z",
    )
    record_quiz_result_in_store(
        progress_path,
        reaction_id="user_2",
        review_grade="easy",
        seen_at="2026-04-29T10:15:00Z",
    )
    loaded = load_quiz_progress(progress_path)

    assert loaded["user_2"].times_seen == 2
    assert loaded["user_2"].count_hard == 1
    assert loaded["user_2"].count_easy == 1
    assert loaded["user_2"].count_again == 0
    assert loaded["user_2"].count_good == 0
    assert loaded["user_2"].last_grade == "easy"
    assert loaded["user_2"].last_seen_at == "2026-04-29T10:15:00Z"
    assert loaded["user_2"].last_reviewed_at == "2026-04-29T10:15:00Z"
    assert loaded["user_2"].interval_days == 5.0
    assert loaded["user_2"].due_at == "2026-05-04T10:15:00Z"


def test_record_quiz_result_in_store_tracks_each_review_grade(tmp_path: Path) -> None:
    progress_path = tmp_path / "quiz_progress.json"

    for grade in ["again", "hard", "good", "easy"]:
        record_quiz_result_in_store(
            progress_path,
            reaction_id="base_9",
            review_grade=grade,
            seen_at="2026-04-29T10:00:00Z",
        )

    loaded = load_quiz_progress(progress_path)

    assert loaded["base_9"].times_seen == 4
    assert loaded["base_9"].count_again == 1
    assert loaded["base_9"].count_hard == 1
    assert loaded["base_9"].count_good == 1
    assert loaded["base_9"].count_easy == 1
    assert loaded["base_9"].last_grade == "easy"
    assert loaded["base_9"].interval_days == 5.0


def test_compute_quiz_progress_totals_can_limit_to_reaction_subset() -> None:
    progress_by_id = {
        "base_1": QuizProgressRecord(reaction_id="base_1", times_seen=2, count_again=1, count_hard=0, count_good=1, count_easy=0),
        "base_2": QuizProgressRecord(reaction_id="base_2", times_seen=3, count_again=0, count_hard=1, count_good=2, count_easy=0),
        "user_1": QuizProgressRecord(reaction_id="user_1", times_seen=4, count_again=0, count_hard=1, count_good=1, count_easy=2),
    }

    totals = compute_quiz_progress_totals(progress_by_id, reaction_ids=["base_2", "user_1"])

    assert totals.times_seen == 7
    assert totals.count_again == 0
    assert totals.count_hard == 2
    assert totals.count_good == 3
    assert totals.count_easy == 2


def test_load_quiz_progress_migrates_older_binary_progress_fields(tmp_path: Path) -> None:
    progress_path = tmp_path / "quiz_progress.json"
    progress_path.write_text(
        """{
  "base_1": {
    "reaction_id": "base_1",
    "times_seen": 5,
    "times_correct": 3,
    "times_incorrect": 2,
    "last_seen_at": "2026-04-29T10:00:00Z"
  }
}""",
        encoding="utf-8",
    )

    loaded = load_quiz_progress(progress_path)

    assert loaded["base_1"].times_seen == 5
    assert loaded["base_1"].count_again == 2
    assert loaded["base_1"].count_good == 3
    assert loaded["base_1"].count_hard == 0
    assert loaded["base_1"].count_easy == 0
    assert loaded["base_1"].last_grade is None
    assert loaded["base_1"].last_reviewed_at == "2026-04-29T10:00:00Z"


def test_compute_next_interval_days_uses_small_explicit_grade_rule() -> None:
    unseen = QuizProgressRecord(reaction_id="base_1")
    reviewed = QuizProgressRecord(reaction_id="base_2", interval_days=4.0)

    assert compute_next_interval_days(unseen, "again") == 5 / (24 * 60)
    assert compute_next_interval_days(unseen, "hard") == 1.0
    assert compute_next_interval_days(unseen, "good") == 3.0
    assert compute_next_interval_days(unseen, "easy") == 5.0
    assert compute_next_interval_days(reviewed, "hard") == 6.0
    assert compute_next_interval_days(reviewed, "good") == 8.0
    assert compute_next_interval_days(reviewed, "easy") == 12.0


def test_is_due_checks_due_at_against_current_time() -> None:
    due_record = QuizProgressRecord(reaction_id="base_1", due_at="2026-04-29T09:00:00Z")
    future_record = QuizProgressRecord(reaction_id="base_2", due_at="2026-04-29T11:00:00Z")

    assert is_due(due_record, now_at="2026-04-29T10:00:00Z") is True
    assert is_due(future_record, now_at="2026-04-29T10:00:00Z") is False


def test_summarize_reaction_study_status_marks_missing_progress_as_new() -> None:
    summary = summarize_reaction_study_status(None)

    assert isinstance(summary, ReactionStudyStatus)
    assert summary.status_label == "New"
    assert summary.last_grade_label is None
    assert summary.next_due_at is None
    assert summary.times_seen == 0


def test_summarize_reaction_study_status_formats_due_and_grade_info() -> None:
    progress = QuizProgressRecord(
        reaction_id="base_1",
        times_seen=4,
        count_again=1,
        count_hard=1,
        count_good=2,
        count_easy=0,
        last_grade="good",
        due_at="2026-04-29T09:00:00Z",
    )

    summary = summarize_reaction_study_status(progress, now_at="2026-04-29T10:00:00Z")

    assert summary.status_label == "Due now"
    assert summary.last_grade_label == "Good"
    assert summary.next_due_at == "2026-04-29T09:00:00Z"
    assert summary.count_good == 2


def test_format_review_grade_label_returns_none_for_missing_grade() -> None:
    assert format_review_grade_label(None) is None
