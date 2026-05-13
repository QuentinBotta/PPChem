"""Helpers for loading, validating, and mutating local reaction stores.

This module sits between the Streamlit UI and persisted JSON files. It keeps
identity, validation, and deck-cleanup rules in one place so the UI can stay
thin and the behavior remains testable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from ppchem.decks.deck_mutations import remove_reaction_from_all_decks_file
from ppchem.models.reaction_io import read_reaction_records, write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord

try:
    from rdkit import Chem
    from rdkit.Chem import rdChemReactions
except Exception:
    Chem = None
    rdChemReactions = None


@dataclass(frozen=True)
class UserReactionDeletionResult:
    """Summary of deleting one user reaction plus any affected decks."""

    reaction_id: str
    removed_from_user_store: bool
    affected_deck_ids: list[str]
    affected_deck_names: list[str]


def load_optional_reactions(path: str | Path) -> list[ReactionRecord]:
    """Load a reaction store if it exists, otherwise treat it as empty."""
    input_path = Path(path)
    if not input_path.exists():
        return []
    return read_reaction_records(input_path)


def find_reaction_by_id(records: list[ReactionRecord], reaction_id: str) -> ReactionRecord | None:
    """Find one reaction strictly by stable `reaction_id`."""
    for record in records:
        if record.reaction_id == reaction_id:
            return record
    return None


def validate_unique_reaction_ids(records: list[ReactionRecord]) -> None:
    """Reject merged record lists that reuse the same `reaction_id` twice."""
    seen: set[str] = set()
    duplicates: list[str] = []

    for record in records:
        if record.reaction_id in seen and record.reaction_id not in duplicates:
            duplicates.append(record.reaction_id)
            continue
        seen.add(record.reaction_id)

    if duplicates:
        duplicate_list = ", ".join(duplicates)
        raise ValueError(
            "Duplicate reaction_id values found while loading merged reactions: "
            f"{duplicate_list}. Base and user stores must not share reaction_id values."
        )


def load_app_reactions(
    *,
    base_path: str | Path,
    user_path: str | Path | None = None,
) -> list[ReactionRecord]:
    """Load base reactions plus optional user reactions into one merged list."""
    records = list(read_reaction_records(base_path))
    if user_path is not None:
        records.extend(load_optional_reactions(user_path))
    validate_unique_reaction_ids(records)
    return records


def split_reaction_smiles(reaction_smiles: str) -> tuple[list[str], list[str]]:
    """Parse a reaction SMILES string into non-empty reactant/product tokens."""
    normalized = reaction_smiles.strip()
    if not normalized:
        raise ValueError("Reaction SMILES cannot be empty")
    if ">>" not in normalized:
        raise ValueError("Reaction SMILES must contain '>>'")

    left, right = normalized.split(">>", maxsplit=1)
    reactants = [token for token in left.split(".") if token]
    products = [token for token in right.split(".") if token]

    if not reactants:
        raise ValueError("Reaction SMILES must include at least one reactant")
    if not products:
        raise ValueError("Reaction SMILES must include at least one product")

    return reactants, products


def build_reaction_smiles_from_visual_inputs(
    *,
    reactants_smiles: str,
    products_smiles: str,
) -> str:
    """Join visual-editor inputs into the same reaction SMILES format used everywhere else."""
    normalized_reactants = reactants_smiles.strip()
    normalized_products = products_smiles.strip()

    if not normalized_reactants:
        raise ValueError("Visual editor must include at least one reactant structure")
    if not normalized_products:
        raise ValueError("Visual editor must include at least one product structure")

    reaction_smiles = f"{normalized_reactants}>>{normalized_products}"
    # Reuse the existing parser so visual mode enforces the same minimum shape.
    split_reaction_smiles(reaction_smiles)
    return reaction_smiles


def normalize_user_tags(raw_tags: str) -> list[str]:
    """Normalize user tags by trimming, dropping empties, and de-duplicating."""
    seen: set[str] = set()
    normalized_tags: list[str] = []

    for item in raw_tags.split(","):
        tag = item.strip()
        if not tag:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        normalized_tags.append(tag)

    return normalized_tags


def validate_reaction_with_rdkit(
    reaction_smiles: str,
    reactants: list[str],
    products: list[str],
) -> tuple[bool, list[str]]:
    """Validate a reaction with RDKit when available, otherwise report that fact."""
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


def next_user_reaction_id(records: list[ReactionRecord]) -> str:
    """Choose the lowest unused `user_N` identifier from existing records."""
    used_numbers: set[int] = set()
    for record in records:
        if not record.reaction_id.startswith("user_"):
            continue
        suffix = record.reaction_id.removeprefix("user_")
        if suffix.isdigit():
            used_numbers.add(int(suffix))

    next_number = 1
    while next_number in used_numbers:
        next_number += 1

    return f"user_{next_number}"


def build_user_reaction_record(
    *,
    reaction_smiles: str,
    existing_records: list[ReactionRecord],
    display_name: str = "",
    raw_tags: str = "",
    created_by: str = "streamlit_app",
) -> ReactionRecord:
    """Create a new user-authored reaction record from UI inputs.

    Unknown chemistry metadata remains empty here as well. Manual entry only
    fills fields the user explicitly supplied or the app can derive structurally.
    """
    normalized = reaction_smiles.strip()
    reactants, products = split_reaction_smiles(normalized)
    is_validated, messages = validate_reaction_with_rdkit(normalized, reactants, products)

    if rdChemReactions is not None and Chem is not None and messages:
        raise ValueError("RDKit validation failed: " + "; ".join(messages))

    reaction_id = next_user_reaction_id(existing_records)
    normalized_display_name = display_name.strip() or None
    normalized_tags = normalize_user_tags(raw_tags)

    return ReactionRecord(
        reaction_id=reaction_id,
        source="user",
        created_by=created_by,
        created_at=ReactionRecord.utc_now_iso(),
        reaction_smiles=normalized,
        reactants_smiles=reactants,
        products_smiles=products,
        display_name=normalized_display_name,
        reaction_class=None,
        tags=normalized_tags,
        difficulty=None,
        hint=None,
        notes=None,
        quality={"is_validated": is_validated, "validation_messages": messages},
        provenance={
            "dataset": "user",
            "dataset_record_id": reaction_id,
            "import_version": "manual_entry_v1",
        },
    )


def append_user_reaction(
    *,
    user_path: str | Path,
    reaction_smiles: str,
    existing_records: list[ReactionRecord],
    display_name: str = "",
    raw_tags: str = "",
    created_by: str = "streamlit_app",
) -> ReactionRecord:
    """Append one new user reaction to the user JSON store."""
    user_records = load_optional_reactions(user_path)
    new_record = build_user_reaction_record(
        reaction_smiles=reaction_smiles,
        existing_records=existing_records,
        display_name=display_name,
        raw_tags=raw_tags,
        created_by=created_by,
    )
    write_reaction_records([*user_records, new_record], user_path)
    return new_record


def build_imported_user_reaction_record(
    source_record: ReactionRecord,
    *,
    existing_records: list[ReactionRecord],
    package_reaction_id: str,
    created_by: str = "deck_package_import",
) -> ReactionRecord:
    """Clone an imported/shared reaction into local user space with a new ID.

    We preserve the chemistry payload and provenance trail, but assign a new
    local `reaction_id` so deck imports do not collide with existing records.
    """
    normalized = source_record.reaction_smiles.strip()
    reactants, products = split_reaction_smiles(normalized)
    reaction_id = next_user_reaction_id(existing_records)

    provenance = copy.deepcopy(source_record.provenance)
    provenance.update(
        {
            "dataset": "user",
            "dataset_record_id": reaction_id,
            "import_version": "deck_package_v1",
            "package_original_reaction_id": source_record.reaction_id,
            "package_reaction_id": package_reaction_id,
            "package_original_source": source_record.source,
        }
    )

    return ReactionRecord(
        reaction_id=reaction_id,
        source="user",
        created_by=created_by,
        created_at=ReactionRecord.utc_now_iso(),
        reaction_smiles=normalized,
        reactants_smiles=reactants,
        products_smiles=products,
        display_name=source_record.display_name,
        reaction_class=source_record.reaction_class,
        tags=list(source_record.tags),
        difficulty=source_record.difficulty,
        hint=source_record.hint,
        notes=source_record.notes,
        quality=copy.deepcopy(source_record.quality),
        provenance=provenance,
        extensions=copy.deepcopy(source_record.extensions),
    )


def build_updated_user_reaction_record(
    existing_record: ReactionRecord,
    *,
    reaction_smiles: str,
    display_name: str = "",
    raw_tags: str = "",
) -> ReactionRecord:
    """Build an updated version of an existing user reaction while preserving identity."""
    if existing_record.source != "user":
        raise ValueError("Only user reactions can be updated with this helper")

    normalized = reaction_smiles.strip()
    reactants, products = split_reaction_smiles(normalized)
    is_validated, messages = validate_reaction_with_rdkit(normalized, reactants, products)

    if rdChemReactions is not None and Chem is not None and messages:
        raise ValueError("RDKit validation failed: " + "; ".join(messages))

    return ReactionRecord(
        # Decks and quiz progress refer to this stable ID, so edits must keep it.
        reaction_id=existing_record.reaction_id,
        source=existing_record.source,
        created_by=existing_record.created_by,
        created_at=existing_record.created_at,
        reaction_smiles=normalized,
        reactants_smiles=reactants,
        products_smiles=products,
        display_name=display_name.strip() or None,
        reaction_class=existing_record.reaction_class,
        tags=normalize_user_tags(raw_tags),
        difficulty=existing_record.difficulty,
        hint=existing_record.hint,
        notes=existing_record.notes,
        quality={"is_validated": is_validated, "validation_messages": messages},
        provenance=dict(existing_record.provenance),
        extensions=dict(existing_record.extensions),
    )


def update_user_reaction_in_store(
    *,
    user_path: str | Path,
    reaction_id: str,
    updated_record: ReactionRecord,
) -> ReactionRecord:
    """Replace one stored user reaction by reaction_id.

    Identity is keyed strictly by reaction_id, not list position or JSON order.
    The updated record must preserve the same reaction_id.
    """

    if updated_record.reaction_id != reaction_id:
        raise ValueError("Updated user reaction must preserve reaction_id")
    if updated_record.source != "user":
        raise ValueError("Updated user reaction must keep source='user'")

    user_records = load_optional_reactions(user_path)
    if find_reaction_by_id(user_records, reaction_id) is None:
        raise ValueError(f"Could not find user reaction: {reaction_id}")

    updated_records = [
        updated_record if record.reaction_id == reaction_id else record
        for record in user_records
    ]
    write_reaction_records(updated_records, user_path)
    return updated_record


def delete_user_reaction_from_store(
    *,
    user_path: str | Path,
    reaction_id: str,
) -> bool:
    """Delete one stored user reaction by reaction_id.

    Returns True only when a record with that reaction_id existed.
    """

    user_records = load_optional_reactions(user_path)
    updated_records = [record for record in user_records if record.reaction_id != reaction_id]
    removed = len(updated_records) != len(user_records)
    write_reaction_records(updated_records, user_path)
    return removed


def delete_user_reaction_with_deck_cleanup(
    *,
    user_path: str | Path,
    decks_path: str | Path,
    reaction_id: str,
) -> UserReactionDeletionResult:
    """Delete a user reaction and remove its ID from every referencing deck."""
    user_records = load_optional_reactions(user_path)
    record = find_reaction_by_id(user_records, reaction_id)

    if record is None:
        raise ValueError(f"Could not find user reaction: {reaction_id}")
    if record.source != "user":
        raise ValueError("Only user reactions can be deleted with this helper")

    deck_cleanup_result = remove_reaction_from_all_decks_file(decks_path, reaction_id=reaction_id)
    removed_from_user_store = delete_user_reaction_from_store(user_path=user_path, reaction_id=reaction_id)

    if not removed_from_user_store:
        raise ValueError(f"Could not delete user reaction: {reaction_id}")

    return UserReactionDeletionResult(
        reaction_id=reaction_id,
        removed_from_user_store=True,
        affected_deck_ids=[deck.deck_id for deck in deck_cleanup_result.affected_decks],
        affected_deck_names=[deck.name for deck in deck_cleanup_result.affected_decks],
    )
