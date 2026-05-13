"""Conservative structural filtering for the first app dataset.

This module trims the imported base dataset down to a smaller MVP subset without
adding chemistry interpretation. The browser and quiz read the filtered JSON so
startup stays predictable on student machines.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ppchem.models.reaction_io import read_reaction_records, write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


@dataclass(frozen=True)
class MvpFilterCriteria:
    """Simple structural rules for the first MVP dataset."""

    max_records: int = 5000
    max_reaction_smiles_length: int = 120
    max_reactants: int = 3
    required_product_count: int = 1
    max_component_smiles_length: int = 80


def _record_filter_reasons(record: ReactionRecord, criteria: MvpFilterCriteria) -> list[str]:
    """Return every structural rule that excludes a record from the MVP set."""
    reasons: list[str] = []

    if len(record.reaction_smiles) > criteria.max_reaction_smiles_length:
        reasons.append("reaction_smiles_too_long")

    if len(record.reactants_smiles) > criteria.max_reactants:
        reasons.append("too_many_reactants")

    if len(record.products_smiles) != criteria.required_product_count:
        reasons.append("unexpected_product_count")

    all_components = record.reactants_smiles + record.products_smiles
    if any(len(component) > criteria.max_component_smiles_length for component in all_components):
        reasons.append("component_smiles_too_long")

    return reasons


def filter_mvp_reactions(
    input_path: str | Path,
    output_path: str | Path,
    *,
    report_path: str | Path | None = None,
    criteria: MvpFilterCriteria | None = None,
) -> dict[str, Any]:
    """Create a conservative structurally filtered MVP subset.

    The filter intentionally avoids chemistry interpretation. It only keeps
    records that are shorter and less crowded, then applies a deterministic size
    cap so the first app can load the data comfortably.
    """

    criteria = criteria or MvpFilterCriteria()
    records = read_reaction_records(input_path)

    kept: list[ReactionRecord] = []
    reason_counts: dict[str, int] = {}

    for record in records:
        reasons = _record_filter_reasons(record, criteria)

        if reasons:
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue

        if len(kept) >= criteria.max_records:
            # The size cap is applied after structural checks so the subset stays
            # deterministic for a given input ordering.
            reason = "mvp_size_limit"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue

        kept.append(record)

    write_reaction_records(kept, output_path)

    report = {
        "input_json": str(input_path),
        "output_json": str(output_path),
        "total_input_rows": int(len(records)),
        "total_kept_rows": int(len(kept)),
        "total_filtered_rows": int(len(records) - len(kept)),
        "filtering_criteria": asdict(criteria),
        "filter_reason_counts": reason_counts,
    }

    if report_path is not None:
        report_output = Path(report_path)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
