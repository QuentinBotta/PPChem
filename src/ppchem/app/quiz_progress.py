from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ReviewGradeValue = str


@dataclass
class QuizProgressRecord:
    reaction_id: str
    times_seen: int = 0
    count_again: int = 0
    count_hard: int = 0
    count_good: int = 0
    count_easy: int = 0
    last_grade: str | None = None
    last_seen_at: str | None = None
    last_reviewed_at: str | None = None
    due_at: str | None = None
    interval_days: float | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "QuizProgressRecord":
        # Older progress files stored binary correct/incorrect counts.
        # We migrate them conservatively into the new grade model by mapping:
        # incorrect -> again, correct -> good.
        count_again = value.get("count_again")
        if count_again is None:
            count_again = value.get("times_incorrect", 0)

        count_good = value.get("count_good")
        if count_good is None:
            count_good = value.get("times_correct", 0)

        return cls(
            reaction_id=str(value["reaction_id"]),
            times_seen=int(value.get("times_seen", 0)),
            count_again=int(count_again),
            count_hard=int(value.get("count_hard", 0)),
            count_good=int(count_good),
            count_easy=int(value.get("count_easy", 0)),
            last_grade=value.get("last_grade"),
            last_seen_at=value.get("last_seen_at"),
            last_reviewed_at=value.get("last_reviewed_at", value.get("last_seen_at")),
            due_at=value.get("due_at"),
            interval_days=float(value["interval_days"]) if value.get("interval_days") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuizProgressTotals:
    times_seen: int = 0
    count_again: int = 0
    count_hard: int = 0
    count_good: int = 0
    count_easy: int = 0


@dataclass(frozen=True)
class ReactionStudyStatus:
    status_label: str
    last_grade_label: str | None
    next_due_at: str | None
    times_seen: int
    count_again: int
    count_hard: int
    count_good: int
    count_easy: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def add_days_iso(started_at: str, interval_days: float) -> str:
    started_dt = parse_iso_datetime(started_at)
    due_dt = started_dt + timedelta(days=interval_days)
    return due_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_due(record: QuizProgressRecord, *, now_at: str | None = None) -> bool:
    if record.due_at is None:
        return False

    now_value = now_at or utc_now_iso()
    return parse_iso_datetime(record.due_at) <= parse_iso_datetime(now_value)


def compute_next_interval_days(record: QuizProgressRecord, review_grade: ReviewGradeValue) -> float:
    """Apply a small explicit review rule.

    This is intentionally much simpler than Anki. We only keep one interval field
    and map each review grade to an easy-to-read interval progression:
    - Again: review again very soon (5 minutes)
    - Hard: short delay
    - Good: moderate delay
    - Easy: longer delay
    """

    previous_interval = record.interval_days or 0.0

    if review_grade == "again":
        return 5 / (24 * 60)
    if review_grade == "hard":
        return 1.0 if previous_interval < 1.0 else max(1.0, round(previous_interval * 1.5, 2))
    if review_grade == "good":
        return 3.0 if previous_interval < 1.0 else max(3.0, round(previous_interval * 2.0, 2))
    if review_grade == "easy":
        return 5.0 if previous_interval < 1.0 else max(5.0, round(previous_interval * 3.0, 2))
    raise ValueError(f"Unsupported review grade: {review_grade}")


def load_quiz_progress(path: str | Path) -> dict[str, QuizProgressRecord]:
    progress_path = Path(path)
    if not progress_path.exists():
        return {}

    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Quiz progress store must be a JSON object keyed by reaction_id")

    return {
        reaction_id: QuizProgressRecord.from_dict(value)
        for reaction_id, value in payload.items()
    }


def write_quiz_progress(progress_by_id: dict[str, QuizProgressRecord], path: str | Path) -> None:
    progress_path = Path(path)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        reaction_id: record.to_dict()
        for reaction_id, record in sorted(progress_by_id.items())
    }
    progress_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_quiz_progress(
    progress_by_id: dict[str, QuizProgressRecord],
    *,
    reaction_id: str,
    review_grade: ReviewGradeValue,
    seen_at: str | None = None,
) -> QuizProgressRecord:
    existing = progress_by_id.get(reaction_id)
    if existing is None:
        existing = QuizProgressRecord(reaction_id=reaction_id)

    reviewed_at = seen_at or utc_now_iso()
    interval_days = compute_next_interval_days(existing, review_grade)

    updated = QuizProgressRecord(
        reaction_id=reaction_id,
        times_seen=existing.times_seen + 1,
        count_again=existing.count_again + (1 if review_grade == "again" else 0),
        count_hard=existing.count_hard + (1 if review_grade == "hard" else 0),
        count_good=existing.count_good + (1 if review_grade == "good" else 0),
        count_easy=existing.count_easy + (1 if review_grade == "easy" else 0),
        last_grade=review_grade,
        last_seen_at=reviewed_at,
        last_reviewed_at=reviewed_at,
        due_at=add_days_iso(reviewed_at, interval_days),
        interval_days=interval_days,
    )
    progress_by_id[reaction_id] = updated
    return updated


def record_quiz_result_in_store(
    path: str | Path,
    *,
    reaction_id: str,
    review_grade: ReviewGradeValue,
    seen_at: str | None = None,
) -> QuizProgressRecord:
    progress_by_id = load_quiz_progress(path)
    updated = update_quiz_progress(
        progress_by_id,
        reaction_id=reaction_id,
        review_grade=review_grade,
        seen_at=seen_at,
    )
    write_quiz_progress(progress_by_id, path)
    return updated


def compute_quiz_progress_totals(
    progress_by_id: dict[str, QuizProgressRecord],
    reaction_ids: list[str] | None = None,
) -> QuizProgressTotals:
    if reaction_ids is None:
        selected_records = list(progress_by_id.values())
    else:
        selected_ids = set(reaction_ids)
        selected_records = [
            record
            for reaction_id, record in progress_by_id.items()
            if reaction_id in selected_ids
        ]

    return QuizProgressTotals(
        times_seen=sum(record.times_seen for record in selected_records),
        count_again=sum(record.count_again for record in selected_records),
        count_hard=sum(record.count_hard for record in selected_records),
        count_good=sum(record.count_good for record in selected_records),
        count_easy=sum(record.count_easy for record in selected_records),
    )


def format_review_grade_label(review_grade: str | None) -> str | None:
    if review_grade is None:
        return None

    return {
        "again": "Again",
        "hard": "Hard",
        "good": "Good",
        "easy": "Easy",
    }.get(review_grade, review_grade)


def summarize_reaction_study_status(
    progress: QuizProgressRecord | None,
    *,
    now_at: str | None = None,
) -> ReactionStudyStatus:
    if progress is None:
        return ReactionStudyStatus(
            status_label="New",
            last_grade_label=None,
            next_due_at=None,
            times_seen=0,
            count_again=0,
            count_hard=0,
            count_good=0,
            count_easy=0,
        )

    status_label = "Due now" if is_due(progress, now_at=now_at) else "Scheduled later"
    return ReactionStudyStatus(
        status_label=status_label,
        last_grade_label=format_review_grade_label(progress.last_grade),
        next_due_at=progress.due_at,
        times_seen=progress.times_seen,
        count_again=progress.count_again,
        count_hard=progress.count_hard,
        count_good=progress.count_good,
        count_easy=progress.count_easy,
    )
