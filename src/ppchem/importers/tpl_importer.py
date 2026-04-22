from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception:  # fallback for offline environments
    pd = None

from ppchem.models.reaction_io import write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord

try:
    from rdkit import Chem
    from rdkit.Chem import rdChemReactions
except Exception:  # RDKit may not be available in all environments
    Chem = None
    rdChemReactions = None


REACTION_COLUMN_CANDIDATES = ["reaction_smiles", "rxn_smiles", "rxn", "reaction", "smiles"]
ROW_ID_COLUMN_CANDIDATES = ["id", "tpl_id", "record_id"]


def _detect_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _split_reaction_smiles(reaction_smiles: str) -> tuple[list[str], list[str]]:
    left, right = reaction_smiles.split(">>", maxsplit=1)
    reactants = [token for token in left.split(".") if token]
    products = [token for token in right.split(".") if token]
    return reactants, products


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return bool(pd is not None and pd.isna(value))


def _validate_with_rdkit(reaction_smiles: str, reactants: list[str], products: list[str]) -> tuple[bool, list[str]]:
    messages: list[str] = []
    if rdChemReactions is None or Chem is None:
        return False, ["rdkit_unavailable"]

    try:
        parsed = rdChemReactions.ReactionFromSmarts(reaction_smiles, useSmiles=True)
        if parsed is None:
            messages.append("reaction_parse_failed")
    except Exception as exc:
        messages.append(f"reaction_parse_error:{exc}")

    for side, molecules in (("reactant", reactants), ("product", products)):
        for smiles in molecules:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                messages.append(f"invalid_{side}_smiles:{smiles}")

    return len(messages) == 0, messages


def _load_rows(csv_path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], list[str], str]:
    if pd is not None:
        frame = pd.read_csv(csv_path)
        if max_rows is not None:
            frame = frame.head(max_rows)
        rows = frame.to_dict(orient="records")
        return rows, list(frame.columns), "pandas"

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for idx, row in enumerate(reader):
            if max_rows is not None and idx >= max_rows:
                break
            rows.append(dict(row))
        return rows, list(reader.fieldnames or []), "csv_fallback"


def convert_tpl_csv(
    csv_path: str | Path,
    output_path: str | Path,
    *,
    dataset_name: str = "drfp_tpl",
    import_version: str = "0.1.0",
    max_rows: int | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convert a tpl CSV file into internal JSON records.

    The function intentionally preserves uncertainty. It only maps values present
    in the input CSV and leaves pedagogical fields empty by default.
    """

    csv_path = Path(csv_path)
    rows, columns, loader = _load_rows(csv_path, max_rows)

    reaction_col = _detect_column(columns, REACTION_COLUMN_CANDIDATES)
    if reaction_col is None:
        raise ValueError(
            f"Could not detect reaction column. Tried {REACTION_COLUMN_CANDIDATES}; found columns={columns}"
        )

    row_id_col = _detect_column(columns, ROW_ID_COLUMN_CANDIDATES)

    records: list[ReactionRecord] = []
    skipped: list[dict[str, Any]] = []
    skipped_reason_counts: dict[str, int] = {}

    for index, row in enumerate(rows):
        raw_reaction = row.get(reaction_col)
        if _is_missing(raw_reaction):
            reason = "missing_reaction_smiles"
            skipped.append({"row_index": int(index), "reason": reason})
            skipped_reason_counts[reason] = skipped_reason_counts.get(reason, 0) + 1
            continue

        reaction_smiles = str(raw_reaction).strip()
        if ">>" not in reaction_smiles:
            reason = "reaction_smiles_missing_separator"
            skipped.append({"row_index": int(index), "reason": reason, "value": reaction_smiles})
            skipped_reason_counts[reason] = skipped_reason_counts.get(reason, 0) + 1
            continue

        reactants, products = _split_reaction_smiles(reaction_smiles)
        is_validated, messages = _validate_with_rdkit(reaction_smiles, reactants, products)

        row_id_value = row.get(row_id_col) if row_id_col else None
        record_id = str(row_id_value) if not _is_missing(row_id_value) else str(index)

        record = ReactionRecord(
            reaction_id=f"base_{record_id}",
            source="base",
            created_by="tpl_importer",
            created_at=ReactionRecord.utc_now_iso(),
            reaction_smiles=reaction_smiles,
            reactants_smiles=reactants,
            products_smiles=products,
            display_name=None,
            reaction_class=None,
            tags=[],
            difficulty=None,
            hint=None,
            notes=None,
            quality={"is_validated": is_validated, "validation_messages": messages},
            provenance={
                "dataset": dataset_name,
                "dataset_record_id": f"row_{record_id}",
                "import_version": import_version,
            },
        )
        records.append(record)

    write_reaction_records(records, output_path)

    report = {
        "input_csv": str(csv_path),
        "output_json": str(output_path),
        "row_count_input": int(len(rows)),
        "row_count_output": int(len(records)),
        "row_count_skipped": int(len(skipped)),
        "columns_found": columns,
        "reaction_column_used": reaction_col,
        "row_id_column_used": row_id_col,
        "columns_not_mapped": [column for column in columns if column not in {reaction_col, row_id_col}],
        "loader": loader,
        "skipped_reason_counts": skipped_reason_counts,
        "skipped_rows": skipped,
    }

    if report_path is not None:
        report_output = Path(report_path)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
