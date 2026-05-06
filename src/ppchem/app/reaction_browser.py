from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ppchem.models.reaction_io import read_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


@dataclass(frozen=True)
class BrowserFilters:
    search_text: str = ""
    max_reactants: int | None = None
    source: str = "all"


@dataclass(frozen=True)
class BrowserPagination:
    page_index: int
    page_size: int
    total_results: int
    total_pages: int
    start_index: int
    end_index: int


@dataclass(frozen=True)
class BrowserReactantSliderState:
    max_value: int
    current_value: int


def load_reactions(path: str | Path) -> list[ReactionRecord]:
    return read_reaction_records(path)


def reaction_label(record: ReactionRecord) -> str:
    return record.display_name or record.reaction_id


def reaction_search_text(record: ReactionRecord) -> str:
    parts = [
        record.display_name or "",
        record.reaction_id,
        record.reaction_smiles,
        " ".join(record.tags),
        " ".join(record.reactants_smiles),
        " ".join(record.products_smiles),
    ]
    return " ".join(part for part in parts if part).lower()


def choose_selected_record(
    records: list[ReactionRecord],
    *,
    selected_rows: list[int] | None = None,
    previous_reaction_id: str | None = None,
) -> ReactionRecord | None:
    if not records:
        return None

    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(records):
            return records[selected_index]

    if previous_reaction_id is not None:
        for record in records:
            if record.reaction_id == previous_reaction_id:
                return record

    return records[0]


def filter_reactions(records: list[ReactionRecord], filters: BrowserFilters) -> list[ReactionRecord]:
    filtered = records

    if filters.source == "base":
        filtered = [record for record in filtered if record.source == "base"]
    elif filters.source == "user":
        filtered = [record for record in filtered if record.source == "user"]

    search_text = filters.search_text.strip().lower()
    if search_text:
        filtered = [
            record
            for record in filtered
            if search_text in reaction_search_text(record)
        ]

    if filters.max_reactants is not None:
        filtered = [record for record in filtered if len(record.reactants_smiles) <= filters.max_reactants]

    return filtered


def compute_browser_reactant_slider_state(
    records: list[ReactionRecord],
    *,
    requested_value: int | None,
    fallback_max: int = 3,
) -> BrowserReactantSliderState:
    if fallback_max <= 0:
        raise ValueError("fallback_max must be positive")

    max_value = max((len(record.reactants_smiles) for record in records), default=fallback_max)
    if max_value <= 0:
        max_value = fallback_max

    if requested_value is None:
        current_value = max_value
    else:
        current_value = min(max(requested_value, 1), max_value)

    return BrowserReactantSliderState(
        max_value=max_value,
        current_value=current_value,
    )


def build_browser_page_signature(filters: BrowserFilters, *, page_size: int) -> tuple[str, int | None, str, int]:
    return (
        filters.search_text.strip().lower(),
        filters.max_reactants,
        filters.source,
        page_size,
    )


def compute_browser_pagination(*, total_results: int, page_size: int, requested_page_index: int) -> BrowserPagination:
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    total_pages = max(1, (total_results + page_size - 1) // page_size)
    clamped_page_index = min(max(requested_page_index, 0), total_pages - 1)

    if total_results == 0:
        start_index = 0
        end_index = 0
    else:
        start_index = clamped_page_index * page_size
        end_index = min(start_index + page_size, total_results)

    return BrowserPagination(
        page_index=clamped_page_index,
        page_size=page_size,
        total_results=total_results,
        total_pages=total_pages,
        start_index=start_index,
        end_index=end_index,
    )


def paginate_reactions(records: list[ReactionRecord], pagination: BrowserPagination) -> list[ReactionRecord]:
    return records[pagination.start_index:pagination.end_index]


def records_to_table(records: list[ReactionRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reaction_id": record.reaction_id,
                "label": reaction_label(record),
                "source": record.source,
                "reactants": len(record.reactants_smiles),
                "products": len(record.products_smiles),
                "smiles_length": len(record.reaction_smiles),
            }
            for record in records
        ]
    )
