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
