from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Literal, MutableMapping

from ppchem.app.quiz_progress import QuizProgressRecord, is_due
from ppchem.models.reaction_schema import ReactionRecord

ReviewGrade = Literal["again", "hard", "good", "easy"]


@dataclass(frozen=True)
class QuizStats:
    again: int = 0
    hard: int = 0
    good: int = 0
    easy: int = 0

    @property
    def answered(self) -> int:
        return self.again + self.hard + self.good + self.easy


@dataclass(frozen=True)
class QuizFilters:
    max_reactants: int | None = None
    require_single_product: bool = False


@dataclass(frozen=True)
class QuizSourcePool:
    label: str
    records: list[ReactionRecord]


@dataclass(frozen=True)
class ScheduledQuizSelection:
    record: ReactionRecord | None
    selection_mode: str


@dataclass(frozen=True)
class QuizPoolStatus:
    due_count: int
    unseen_count: int
    reviewed_not_due_count: int
    relearning_count: int

    @property
    def eligible_count(self) -> int:
        return self.due_count + self.unseen_count + self.relearning_count


def filter_quiz_records(records: list[ReactionRecord], filters: QuizFilters) -> list[ReactionRecord]:
    filtered = records

    if filters.max_reactants is not None:
        filtered = [record for record in filtered if len(record.reactants_smiles) <= filters.max_reactants]

    if filters.require_single_product:
        filtered = [record for record in filtered if len(record.products_smiles) == 1]

    return filtered


def recent_history_limit(pool_size: int) -> int:
    if pool_size <= 1:
        return 1
    return min(5, pool_size - 1)


def update_recent_history(history: list[str], reaction_id: str, *, max_length: int) -> list[str]:
    trimmed_history = [item for item in history if item != reaction_id]
    trimmed_history.append(reaction_id)

    if max_length <= 0:
        return []

    return trimmed_history[-max_length:]


def choose_quiz_source_pool(
    all_records: list[ReactionRecord],
    *,
    deck_records: list[ReactionRecord] | None = None,
    deck_name: str | None = None,
    browser_subset_records: list[ReactionRecord] | None = None,
    use_browser_subset: bool = False,
) -> QuizSourcePool:
    records = deck_records if deck_records is not None else all_records
    label = deck_name or "All reactions"

    if use_browser_subset:
        browser_ids = {record.reaction_id for record in (browser_subset_records or [])}
        records = [record for record in records if record.reaction_id in browser_ids]
        if deck_name:
            label = f"Deck: {deck_name} + Browser subset"
        else:
            label = "Browser subset"

    return QuizSourcePool(label=label, records=records)


def build_quiz_source_key(
    records: list[ReactionRecord],
    *,
    source_label: str,
    allow_study_ahead: bool,
) -> str:
    reaction_ids = "|".join(record.reaction_id for record in records)
    return f"{source_label}|study_ahead={int(allow_study_ahead)}|records={reaction_ids}"


def update_relearning_reaction_ids(
    relearning_reaction_ids: list[str],
    *,
    reaction_id: str,
    keep_in_relearning: bool,
) -> list[str]:
    updated_ids = [item for item in relearning_reaction_ids if item != reaction_id]
    if keep_in_relearning:
        updated_ids.append(reaction_id)
    return updated_ids


def reset_quiz_session_state(session_state: MutableMapping[str, Any]) -> None:
    session_state["quiz_count_again"] = 0
    session_state["quiz_count_hard"] = 0
    session_state["quiz_count_good"] = 0
    session_state["quiz_count_easy"] = 0
    session_state["quiz_revealed"] = False
    session_state["quiz_last_result"] = None
    session_state["quiz_recent_reaction_ids"] = []
    session_state["quiz_relearning_reaction_ids"] = []
    session_state["quiz_reaction_id"] = None
    session_state["quiz_selection_mode"] = None


def sync_quiz_session_source(session_state: MutableMapping[str, Any], source_key: str) -> bool:
    previous_key = session_state.get("quiz_source_key")
    if previous_key == source_key:
        return False

    reset_quiz_session_state(session_state)
    session_state["quiz_source_key"] = source_key
    return True


def choose_random_reaction(
    records: list[ReactionRecord],
    *,
    previous_reaction_id: str | None = None,
    recent_reaction_ids: list[str] | None = None,
    rng: random.Random | None = None,
) -> ReactionRecord:
    if not records:
        raise ValueError("Cannot choose a quiz reaction from an empty record list")

    if len(records) == 1:
        return records[0]

    random_source = rng or random
    recent_ids = set(recent_reaction_ids or [])
    candidates = [record for record in records if record.reaction_id not in recent_ids]

    if not candidates:
        candidates = [record for record in records if record.reaction_id != previous_reaction_id]

    if not candidates:
        candidates = records

    return random_source.choice(candidates)


def format_quiz_prompt(record: ReactionRecord) -> list[str]:
    return record.reactants_smiles


def format_quiz_answer(record: ReactionRecord) -> list[str]:
    return record.products_smiles


def review_grade_label(grade: ReviewGrade) -> str:
    return {
        "again": "Again",
        "hard": "Hard",
        "good": "Good",
        "easy": "Easy",
    }[grade]


def summarize_quiz_pool(
    records: list[ReactionRecord],
    *,
    progress_by_id: dict[str, QuizProgressRecord],
    relearning_reaction_ids: list[str] | None = None,
    now_at: str | None = None,
) -> QuizPoolStatus:
    due_count = 0
    unseen_count = 0
    reviewed_not_due_count = 0
    relearning_count = 0
    relearning_ids = set(relearning_reaction_ids or [])

    for record in records:
        if record.reaction_id in relearning_ids:
            relearning_count += 1
            continue
        progress = progress_by_id.get(record.reaction_id)
        if progress is None:
            unseen_count += 1
        elif is_due(progress, now_at=now_at):
            due_count += 1
        else:
            reviewed_not_due_count += 1

    return QuizPoolStatus(
        due_count=due_count,
        unseen_count=unseen_count,
        reviewed_not_due_count=reviewed_not_due_count,
        relearning_count=relearning_count,
    )


def choose_scheduled_quiz_reaction(
    records: list[ReactionRecord],
    *,
    progress_by_id: dict[str, QuizProgressRecord],
    allow_study_ahead: bool = False,
    relearning_reaction_ids: list[str] | None = None,
    previous_reaction_id: str | None = None,
    recent_reaction_ids: list[str] | None = None,
    now_at: str | None = None,
    rng: random.Random | None = None,
) -> ScheduledQuizSelection:
    if not records:
        raise ValueError("Cannot choose a scheduled quiz reaction from an empty record list")

    relearning_ids = set(relearning_reaction_ids or [])
    relearning_records = [record for record in records if record.reaction_id in relearning_ids]
    if relearning_records:
        chosen = choose_random_reaction(
            relearning_records,
            previous_reaction_id=previous_reaction_id,
            recent_reaction_ids=recent_reaction_ids,
            rng=rng,
        )
        return ScheduledQuizSelection(record=chosen, selection_mode="relearning")

    due_records = [
        record
        for record in records
        if (progress := progress_by_id.get(record.reaction_id)) is not None and is_due(progress, now_at=now_at)
    ]
    if due_records:
        chosen = choose_random_reaction(
            due_records,
            previous_reaction_id=previous_reaction_id,
            recent_reaction_ids=recent_reaction_ids,
            rng=rng,
        )
        return ScheduledQuizSelection(record=chosen, selection_mode="due")

    unseen_records = [record for record in records if record.reaction_id not in progress_by_id]
    if unseen_records:
        chosen = choose_random_reaction(
            unseen_records,
            previous_reaction_id=previous_reaction_id,
            recent_reaction_ids=recent_reaction_ids,
            rng=rng,
        )
        return ScheduledQuizSelection(record=chosen, selection_mode="unseen")

    if allow_study_ahead:
        reviewed_not_due_records = [
            record
            for record in records
            if (progress := progress_by_id.get(record.reaction_id)) is not None and not is_due(progress, now_at=now_at)
        ]
        if reviewed_not_due_records:
            chosen = choose_random_reaction(
                reviewed_not_due_records,
                previous_reaction_id=previous_reaction_id,
                recent_reaction_ids=recent_reaction_ids,
                rng=rng,
            )
            return ScheduledQuizSelection(record=chosen, selection_mode="study_ahead")

    return ScheduledQuizSelection(record=None, selection_mode="complete")
