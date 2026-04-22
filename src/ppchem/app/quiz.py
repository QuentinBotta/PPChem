from __future__ import annotations

import random
from dataclasses import dataclass

from ppchem.models.reaction_schema import ReactionRecord


@dataclass(frozen=True)
class QuizStats:
    correct: int = 0
    incorrect: int = 0

    @property
    def answered(self) -> int:
        return self.correct + self.incorrect


@dataclass(frozen=True)
class QuizFilters:
    max_reactants: int | None = None
    require_single_product: bool = False


@dataclass(frozen=True)
class QuizSourcePool:
    label: str
    records: list[ReactionRecord]


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
