from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ppchem.app.reaction_sources import build_imported_user_reaction_record, load_optional_reactions
from ppchem.decks.deck_io import read_deck_records, write_deck_records
from ppchem.decks.deck_mutations import choose_unique_deck_id
from ppchem.decks.deck_resolution import resolve_deck_records
from ppchem.decks.deck_schema import DeckRecord
from ppchem.models.reaction_io import write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


DUPLICATE_DECISION_USE_EXISTING = "use_existing"
DUPLICATE_DECISION_IMPORT_AS_NEW = "import_as_new"
DECK_COLLISION_CHOICE_MERGE = "merge_into_existing"
DECK_COLLISION_CHOICE_SEPARATE = "create_separate_imported_deck"
PACKAGE_FORMAT_VERSION = "portable_deck_package_v1"


@dataclass(frozen=True)
class PortableDeckReactionEntry:
    package_reaction_id: str
    reaction: ReactionRecord


@dataclass(frozen=True)
class PortableDeckPackage:
    format_version: str
    deck_id: str
    name: str
    description: str
    reaction_refs: list[str]
    reactions: list[PortableDeckReactionEntry]


@dataclass(frozen=True)
class DuplicateReactionCandidate:
    package_reaction_id: str
    imported_reaction: ReactionRecord
    existing_local_reaction: ReactionRecord


@dataclass(frozen=True)
class DeckCollisionCandidate:
    deck_id: str
    name: str
    description: str
    collision_reasons: list[str]


@dataclass(frozen=True)
class PortableDeckImportAnalysis:
    package: PortableDeckPackage
    no_conflict_reaction_ids: list[str]
    duplicate_candidates: list[DuplicateReactionCandidate]
    deck_collision_candidates: list[DeckCollisionCandidate]


@dataclass(frozen=True)
class PortableDeckImportResult:
    final_deck: DeckRecord
    final_deck_id: str
    final_deck_name: str
    deck_renamed: bool
    deck_name_changed: bool
    merged_into_existing_deck: bool
    deck_reaction_ids_added_count: int
    created_reactions: list[ReactionRecord]
    package_reaction_id_to_final_reaction_id: dict[str, str]
    used_existing_reaction_ids: list[str]


def deduplicate_reaction_ids_preserving_order(reaction_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []

    for reaction_id in reaction_ids:
        if reaction_id in seen:
            continue
        seen.add(reaction_id)
        deduplicated.append(reaction_id)

    return deduplicated


def choose_unique_deck_name(base_name: str, existing_names: set[str]) -> str:
    if base_name not in existing_names:
        return base_name

    suffix = 2
    while True:
        candidate = f"{base_name} {suffix}"
        if candidate not in existing_names:
            return candidate
        suffix += 1


def build_imported_deck_name(base_name: str, existing_names: set[str]) -> str:
    preferred_name = f"{base_name} (Imported)"
    return choose_unique_deck_name(preferred_name, existing_names)


def _reaction_record_to_package_dict(record: ReactionRecord) -> dict[str, Any]:
    return record.to_dict()


def export_deck_package_json(
    deck: DeckRecord,
    *,
    reaction_lookup: dict[str, ReactionRecord],
) -> str:
    resolution = resolve_deck_records(deck, reaction_lookup)
    if resolution.missing_reaction_ids:
        raise ValueError(
            "Cannot export a portable deck package when deck reactions are missing locally: "
            + ", ".join(resolution.missing_reaction_ids[:5])
            + (" ..." if len(resolution.missing_reaction_ids) > 5 else "")
        )

    unique_reaction_entries: list[PortableDeckReactionEntry] = []
    seen_reaction_ids: set[str] = set()
    for reaction_id in deck.reaction_ids:
        if reaction_id in seen_reaction_ids:
            continue
        seen_reaction_ids.add(reaction_id)
        reaction = reaction_lookup[reaction_id]
        unique_reaction_entries.append(
            PortableDeckReactionEntry(
                package_reaction_id=reaction_id,
                reaction=reaction,
            )
        )

    payload = {
        "format_version": PACKAGE_FORMAT_VERSION,
        "deck": {
            "deck_id": deck.deck_id,
            "name": deck.name,
            "description": deck.description,
            "reaction_refs": list(deck.reaction_ids),
        },
        "reactions": [
            {
                "package_reaction_id": entry.package_reaction_id,
                "reaction": _reaction_record_to_package_dict(entry.reaction),
            }
            for entry in unique_reaction_entries
        ],
    }
    return json.dumps(payload, indent=2)


def parse_deck_package_json(raw_json: str) -> PortableDeckPackage:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Deck package JSON is invalid: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Deck package JSON must be a JSON object")

    format_version = payload.get("format_version")
    if format_version != PACKAGE_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported deck package format_version: {format_version!r}. "
            f"Expected {PACKAGE_FORMAT_VERSION!r}"
        )

    deck_payload = payload.get("deck")
    if not isinstance(deck_payload, dict):
        raise ValueError("Deck package must contain a 'deck' object")

    deck_id = str(deck_payload.get("deck_id", "")).strip()
    name = str(deck_payload.get("name", "")).strip()
    if not deck_id:
        raise ValueError("Deck package deck_id cannot be empty")
    if not name:
        raise ValueError("Deck package deck name cannot be empty")

    description_value = deck_payload.get("description", "")
    description = "" if description_value is None else str(description_value)

    reaction_refs_payload = deck_payload.get("reaction_refs")
    if not isinstance(reaction_refs_payload, list) or any(not isinstance(item, str) or not item for item in reaction_refs_payload):
        raise ValueError("Deck package reaction_refs must be a list of non-empty strings")
    reaction_refs = deduplicate_reaction_ids_preserving_order(reaction_refs_payload)

    reactions_payload = payload.get("reactions")
    if not isinstance(reactions_payload, list):
        raise ValueError("Deck package must contain a 'reactions' list")

    reactions: list[PortableDeckReactionEntry] = []
    seen_package_reaction_ids: set[str] = set()
    for item in reactions_payload:
        if not isinstance(item, dict):
            raise ValueError("Each deck package reaction entry must be a JSON object")

        package_reaction_id = str(item.get("package_reaction_id", "")).strip()
        if not package_reaction_id:
            raise ValueError("Each deck package reaction entry must include package_reaction_id")
        if package_reaction_id in seen_package_reaction_ids:
            raise ValueError(f"Duplicate package_reaction_id found in deck package: {package_reaction_id}")

        reaction_payload = item.get("reaction")
        if not isinstance(reaction_payload, dict):
            raise ValueError("Each deck package reaction entry must include a 'reaction' object")

        reactions.append(
            PortableDeckReactionEntry(
                package_reaction_id=package_reaction_id,
                reaction=ReactionRecord.from_dict(reaction_payload),
            )
        )
        seen_package_reaction_ids.add(package_reaction_id)

    reaction_entry_lookup = {entry.package_reaction_id: entry for entry in reactions}
    missing_refs = [reaction_ref for reaction_ref in reaction_refs if reaction_ref not in reaction_entry_lookup]
    if missing_refs:
        raise ValueError(
            "Deck package reaction_refs contain references without payloads: "
            + ", ".join(missing_refs)
        )

    return PortableDeckPackage(
        format_version=format_version,
        deck_id=deck_id,
        name=name,
        description=description,
        reaction_refs=reaction_refs,
        reactions=reactions,
    )


def analyze_deck_package_import(
    *,
    raw_json: str,
    local_records: list[ReactionRecord],
    existing_decks: list[DeckRecord] | None = None,
) -> PortableDeckImportAnalysis:
    package = parse_deck_package_json(raw_json)
    duplicate_candidates: list[DuplicateReactionCandidate] = []
    no_conflict_reaction_ids: list[str] = []
    deck_collision_candidates: list[DeckCollisionCandidate] = []

    local_matches_by_smiles: dict[str, list[ReactionRecord]] = {}
    for record in local_records:
        local_matches_by_smiles.setdefault(record.reaction_smiles, []).append(record)

    for entry in package.reactions:
        exact_matches = local_matches_by_smiles.get(entry.reaction.reaction_smiles, [])
        if exact_matches:
            duplicate_candidates.append(
                DuplicateReactionCandidate(
                    package_reaction_id=entry.package_reaction_id,
                    imported_reaction=entry.reaction,
                    existing_local_reaction=exact_matches[0],
                )
            )
            continue
        no_conflict_reaction_ids.append(entry.package_reaction_id)

    for deck in existing_decks or []:
        collision_reasons: list[str] = []
        if deck.deck_id == package.deck_id:
            collision_reasons.append("same deck_id")
        if deck.name == package.name:
            collision_reasons.append("same visible name")
        if collision_reasons:
            deck_collision_candidates.append(
                DeckCollisionCandidate(
                    deck_id=deck.deck_id,
                    name=deck.name,
                    description=deck.description,
                    collision_reasons=collision_reasons,
                )
            )

    return PortableDeckImportAnalysis(
        package=package,
        no_conflict_reaction_ids=no_conflict_reaction_ids,
        duplicate_candidates=duplicate_candidates,
        deck_collision_candidates=deck_collision_candidates,
    )


def finalize_deck_package_import_into_store(
    *,
    analysis: PortableDeckImportAnalysis,
    duplicate_decisions: dict[str, str],
    local_records: list[ReactionRecord],
    user_path: str | Path,
    decks_path: str | Path,
    deck_collision_choice: str = DECK_COLLISION_CHOICE_SEPARATE,
    merge_target_deck_id: str | None = None,
) -> PortableDeckImportResult:
    reaction_entry_lookup = {entry.package_reaction_id: entry.reaction for entry in analysis.package.reactions}
    duplicate_lookup = {candidate.package_reaction_id: candidate for candidate in analysis.duplicate_candidates}

    for package_reaction_id in duplicate_lookup:
        decision = duplicate_decisions.get(package_reaction_id)
        if decision not in {DUPLICATE_DECISION_USE_EXISTING, DUPLICATE_DECISION_IMPORT_AS_NEW}:
            raise ValueError(
                f"Duplicate decision missing or invalid for package_reaction_id: {package_reaction_id}"
            )

    existing_user_records = load_optional_reactions(user_path)
    records_for_id_assignment = list(local_records)
    known_reaction_ids = {record.reaction_id for record in records_for_id_assignment}
    for user_record in existing_user_records:
        if user_record.reaction_id in known_reaction_ids:
            continue
        records_for_id_assignment.append(user_record)
        known_reaction_ids.add(user_record.reaction_id)
    created_reactions: list[ReactionRecord] = []
    package_reaction_id_to_final_reaction_id: dict[str, str] = {}
    used_existing_reaction_ids: list[str] = []

    for package_reaction_id in analysis.package.reaction_refs:
        if package_reaction_id in package_reaction_id_to_final_reaction_id:
            continue

        duplicate_candidate = duplicate_lookup.get(package_reaction_id)
        if duplicate_candidate is not None:
            decision = duplicate_decisions[package_reaction_id]
            if decision == DUPLICATE_DECISION_USE_EXISTING:
                final_reaction_id = duplicate_candidate.existing_local_reaction.reaction_id
                package_reaction_id_to_final_reaction_id[package_reaction_id] = final_reaction_id
                if final_reaction_id not in used_existing_reaction_ids:
                    used_existing_reaction_ids.append(final_reaction_id)
                continue

        source_reaction = reaction_entry_lookup[package_reaction_id]
        imported_record = build_imported_user_reaction_record(
            source_reaction,
            existing_records=records_for_id_assignment,
            package_reaction_id=package_reaction_id,
        )
        created_reactions.append(imported_record)
        records_for_id_assignment.append(imported_record)
        package_reaction_id_to_final_reaction_id[package_reaction_id] = imported_record.reaction_id

    if created_reactions:
        write_reaction_records([*existing_user_records, *created_reactions], user_path)

    final_reaction_ids = deduplicate_reaction_ids_preserving_order(
        [package_reaction_id_to_final_reaction_id[reaction_ref] for reaction_ref in analysis.package.reaction_refs]
    )

    decks_store_path = Path(decks_path)
    existing_decks = read_deck_records(decks_store_path) if decks_store_path.exists() else []

    if analysis.deck_collision_candidates and deck_collision_choice not in {
        DECK_COLLISION_CHOICE_MERGE,
        DECK_COLLISION_CHOICE_SEPARATE,
    }:
        raise ValueError("Deck collision choice is required when the imported deck conflicts with an existing deck")

    if deck_collision_choice == DECK_COLLISION_CHOICE_MERGE:
        merge_target = next((deck for deck in existing_decks if deck.deck_id == merge_target_deck_id), None)
        if merge_target is None:
            raise ValueError("Choose an existing deck to merge into")

        merged_reaction_ids = deduplicate_reaction_ids_preserving_order(
            [*merge_target.reaction_ids, *final_reaction_ids]
        )
        added_count = len(merged_reaction_ids) - len(merge_target.reaction_ids)
        final_deck = DeckRecord(
            deck_id=merge_target.deck_id,
            name=merge_target.name,
            description=merge_target.description,
            reaction_ids=merged_reaction_ids,
        )
        updated_decks = [
            final_deck if deck.deck_id == merge_target.deck_id else deck
            for deck in existing_decks
        ]
        write_deck_records(updated_decks, decks_store_path)
        return PortableDeckImportResult(
            final_deck=final_deck,
            final_deck_id=final_deck.deck_id,
            final_deck_name=final_deck.name,
            deck_renamed=False,
            deck_name_changed=False,
            merged_into_existing_deck=True,
            deck_reaction_ids_added_count=added_count,
            created_reactions=created_reactions,
            package_reaction_id_to_final_reaction_id=package_reaction_id_to_final_reaction_id,
            used_existing_reaction_ids=used_existing_reaction_ids,
        )

    existing_deck_ids = {deck.deck_id for deck in existing_decks}
    existing_deck_names = {deck.name for deck in existing_decks}
    final_deck_id = choose_unique_deck_id(analysis.package.deck_id, existing_deck_ids)

    final_deck_name = analysis.package.name
    if analysis.deck_collision_candidates:
        final_deck_name = build_imported_deck_name(analysis.package.name, existing_deck_names)
    elif final_deck_name in existing_deck_names:
        final_deck_name = choose_unique_deck_name(final_deck_name, existing_deck_names)

    final_deck = DeckRecord(
        deck_id=final_deck_id,
        name=final_deck_name,
        description=analysis.package.description,
        reaction_ids=final_reaction_ids,
    )
    write_deck_records([*existing_decks, final_deck], decks_store_path)

    return PortableDeckImportResult(
        final_deck=final_deck,
        final_deck_id=final_deck_id,
        final_deck_name=final_deck.name,
        deck_renamed=final_deck_id != analysis.package.deck_id,
        deck_name_changed=final_deck.name != analysis.package.name,
        merged_into_existing_deck=False,
        deck_reaction_ids_added_count=len(final_reaction_ids),
        created_reactions=created_reactions,
        package_reaction_id_to_final_reaction_id=package_reaction_id_to_final_reaction_id,
        used_existing_reaction_ids=used_existing_reaction_ids,
    )
