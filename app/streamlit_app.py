from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ppchem.app.quiz import (
    QuizFilters,
    choose_quiz_source_pool,
    choose_random_reaction,
    filter_quiz_records,
    recent_history_limit,
    update_recent_history,
)
from ppchem.app.reaction_browser import BrowserFilters, choose_selected_record, filter_reactions, load_reactions, records_to_table
from ppchem.app.rendering import build_molecule_grid_image, build_reaction_image
from ppchem.app.reaction_sources import (
    append_user_reaction,
    build_updated_user_reaction_record,
    load_app_reactions,
    update_user_reaction_in_store,
)
from ppchem.decks.deck_io import read_deck_records
from ppchem.decks.deck_mutations import add_reaction_to_decks_file, remove_reaction_from_decks_file
from ppchem.decks.deck_resolution import build_reaction_lookup, resolve_deck_records
from ppchem.decks.deck_schema import DeckRecord
from ppchem.models.reaction_schema import ReactionRecord

try:
    from rdkit import Chem
    from rdkit.Chem import Draw, rdChemReactions
    RDKIT_IMPORT_ERROR = None
except Exception as exc:
    Chem = None
    Draw = None
    rdChemReactions = None
    RDKIT_IMPORT_ERROR = exc


DATASET_PATH = ROOT_DIR / "data" / "processed" / "reactions.mvp.json"
USER_DATASET_PATH = ROOT_DIR / "data" / "processed" / "reactions.user.json"
DECKS_PATH = ROOT_DIR / "data" / "decks" / "sample_decks.json"


@st.cache_data(show_spinner="Loading reaction datasets...")
def cached_load_reactions(base_path: str, user_path: str) -> list[ReactionRecord]:
    return load_app_reactions(base_path=base_path, user_path=user_path)


@st.cache_data(show_spinner="Loading decks...")
def cached_load_decks(path: str) -> list[DeckRecord]:
    return read_deck_records(path)


def render_molecule_grid(title: str, smiles_values: list[str]) -> None:
    st.subheader(title)

    result = build_molecule_grid_image(smiles_values, chem_module=Chem, draw_module=Draw)

    if result.image is not None:
        st.image(result.image)

    for smiles in result.fallback_smiles:
        st.code(smiles, language="text")


def render_reaction_image(record: ReactionRecord) -> None:
    result = build_reaction_image(record.reaction_smiles, reaction_module=rdChemReactions, draw_module=Draw)

    if result.image is not None:
        st.image(result.image)
        return

    if result.fallback_reason:
        if RDKIT_IMPORT_ERROR is not None:
            st.info(f"{result.fallback_reason} Install the optional RDKit support to enable visual rendering.")
        else:
            st.info(result.fallback_reason)


def render_reaction_core_detail(record: ReactionRecord) -> None:
    st.header(record.display_name or record.reaction_id)

    st.caption(
        f"Source: {record.source} | "
        f"{len(record.reactants_smiles)} reactant component(s), {len(record.products_smiles)} product component(s)"
    )
    render_reaction_image(record)

    st.subheader("Reaction SMILES")
    st.code(record.reaction_smiles, language="text")

    left, right = st.columns(2)
    with left:
        render_molecule_grid("Reactants", record.reactants_smiles)
    with right:
        render_molecule_grid("Products", record.products_smiles)

    with st.expander("Provenance and quality", expanded=False):
        st.json(
            {
                "reaction_id": record.reaction_id,
                "source": record.source,
                "created_by": record.created_by,
                "provenance": record.provenance,
                "quality": record.quality,
            }
        )


def format_tags_for_input(tags: list[str]) -> str:
    return ", ".join(tags)


def render_user_reaction_edit_panel(record: ReactionRecord, user_path: Path) -> None:
    st.subheader("Edit Reaction")
    st.caption(
        "Only user-authored fields are editable here. "
        "Reaction ID, source, and creation metadata stay fixed."
    )

    edit_message = st.session_state.pop("browser_edit_reaction_message", None)
    edit_level = st.session_state.pop("browser_edit_reaction_level", "success")
    if edit_message:
        if edit_level == "warning":
            st.warning(edit_message)
        else:
            st.success(edit_message)

    with st.form(f"edit_user_reaction_{record.reaction_id}"):
        reaction_smiles = st.text_input(
            "Reaction SMILES",
            value=record.reaction_smiles,
            key=f"edit_reaction_smiles_{record.reaction_id}",
        )
        display_name = st.text_input(
            "Display name (optional)",
            value=record.display_name or "",
            key=f"edit_display_name_{record.reaction_id}",
        )
        tags_text = st.text_input(
            "Tags (optional, comma-separated)",
            value=format_tags_for_input(record.tags),
            key=f"edit_tags_{record.reaction_id}",
        )
        submitted = st.form_submit_button("Save reaction edits")

    if not submitted:
        return

    try:
        updated_record = build_updated_user_reaction_record(
            record,
            reaction_smiles=reaction_smiles,
            display_name=display_name,
            raw_tags=tags_text,
        )
        update_user_reaction_in_store(
            user_path=user_path,
            reaction_id=record.reaction_id,
            updated_record=updated_record,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    cached_load_reactions.clear()
    st.session_state.browser_selected_reaction_id = record.reaction_id
    st.session_state.browser_edit_reaction_level = "success"
    st.session_state.browser_edit_reaction_message = f"Saved edits for {record.reaction_id}."
    st.rerun()


def render_deck_action_panel(record: ReactionRecord, decks: list[DeckRecord], decks_path: Path) -> None:
    st.subheader("Decks")

    deck_action_message = st.session_state.pop("browser_deck_action_message", None)
    deck_action_level = st.session_state.pop("browser_deck_action_level", "success")
    if deck_action_message:
        if deck_action_level == "warning":
            st.warning(deck_action_message)
        elif deck_action_level == "info":
            st.info(deck_action_message)
        else:
            st.success(deck_action_message)

    deck_options = [""] + [deck.deck_id for deck in decks]
    deck_labels = {"": "Choose an existing deck"}
    deck_labels.update({deck.deck_id: deck.name for deck in decks})

    with st.form(f"add_to_deck_{record.reaction_id}"):
        selected_deck_id = st.selectbox(
            "Existing deck",
            deck_options,
            format_func=lambda deck_id: deck_labels[deck_id],
            key=f"browser_deck_select_{record.reaction_id}",
        )
        new_deck_name = st.text_input(
            "New deck name",
            value="",
            placeholder="Create a new deck and add this reaction",
            key=f"browser_new_deck_name_{record.reaction_id}",
        )
        submitted = st.form_submit_button("Add selected reaction to deck")

    if not submitted:
        return

    try:
        result = add_reaction_to_decks_file(
            decks_path,
            reaction_id=record.reaction_id,
            selected_deck_id=selected_deck_id,
            new_deck_name=new_deck_name,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    cached_load_decks.clear()

    if result.created_new_deck and result.added_reaction:
        message = f"Created deck '{result.deck.name}' and added {record.reaction_id}."
    elif result.created_new_deck:
        message = f"Created deck '{result.deck.name}'."
    elif result.added_reaction:
        message = f"Added {record.reaction_id} to '{result.deck.name}'."
    else:
        message = f"{record.reaction_id} is already in '{result.deck.name}'."
        st.session_state.browser_deck_action_level = "info"

    if "browser_deck_action_level" not in st.session_state:
        st.session_state.browser_deck_action_level = "success"
    st.session_state.browser_deck_action_message = message
    st.rerun()


def render_deck_inspector_panel(
    records: list[ReactionRecord],
    decks: list[DeckRecord],
    decks_path: Path,
    *,
    title: str,
    selectbox_label: str,
    empty_selection_caption: str,
    remove_button_label: str,
    state_prefix: str,
) -> None:
    st.subheader(title)

    message_key = f"{state_prefix}_message"
    level_key = f"{state_prefix}_level"
    selected_deck_key = f"{state_prefix}_selected_deck_id"

    deck_action_message = st.session_state.pop(message_key, None)
    deck_action_level = st.session_state.pop(level_key, "success")
    if deck_action_message:
        if deck_action_level == "warning":
            st.warning(deck_action_message)
        elif deck_action_level == "info":
            st.info(deck_action_message)
        else:
            st.success(deck_action_message)

    deck_options = [""] + [deck.deck_id for deck in decks]
    deck_labels = {"": "Choose a deck to inspect"}
    deck_labels.update({deck.deck_id: deck.name for deck in decks})

    selected_deck_id = st.selectbox(
        selectbox_label,
        deck_options,
        format_func=lambda deck_id: deck_labels[deck_id],
        key=selected_deck_key,
    )

    if not selected_deck_id:
        st.caption(empty_selection_caption)
        return

    selected_deck = next((deck for deck in decks if deck.deck_id == selected_deck_id), None)
    if selected_deck is None:
        st.warning("Could not find the selected deck.")
        return

    resolution = resolve_deck_records(selected_deck, build_reaction_lookup(records))

    st.caption(f"Deck: {selected_deck.name} | Stored IDs: {len(selected_deck.reaction_ids)} | Resolved records: {len(resolution.records)}")
    if selected_deck.description:
        st.write(selected_deck.description)

    if resolution.missing_reaction_ids:
        st.warning(
            "This deck contains missing reaction IDs: "
            + ", ".join(resolution.missing_reaction_ids[:5])
            + (" ..." if len(resolution.missing_reaction_ids) > 5 else "")
        )

    if resolution.records:
        for resolved_record in resolution.records:
            summary_label = resolved_record.display_name or resolved_record.reaction_id
            smiles_preview = resolved_record.reaction_smiles[:100]
            if len(resolved_record.reaction_smiles) > 100:
                smiles_preview += "..."
            st.write(f"- {summary_label}: `{smiles_preview}`")
    else:
        st.info("This deck currently has no resolved reactions to show.")

    removal_options = [""]
    removal_labels = {"": "Choose a reaction to remove"}
    for reaction_id in selected_deck.reaction_ids:
        record = find_record_by_id(resolution.records, reaction_id)
        if record is not None:
            smiles_preview = record.reaction_smiles[:80]
            if len(record.reaction_smiles) > 80:
                smiles_preview += "..."
            removal_labels[reaction_id] = f"{reaction_id} | {smiles_preview}"
        else:
            removal_labels[reaction_id] = f"{reaction_id} | missing from loaded dataset"
        removal_options.append(reaction_id)

    with st.form(f"{state_prefix}_remove_from_deck_{selected_deck.deck_id}"):
        reaction_id_to_remove = st.selectbox(
            "Reaction to remove",
            removal_options,
            format_func=lambda reaction_id: removal_labels[reaction_id],
            key=f"{state_prefix}_remove_reaction_{selected_deck.deck_id}",
        )
        submitted = st.form_submit_button(remove_button_label)

    if not submitted:
        return

    if not reaction_id_to_remove:
        st.warning("Choose a reaction to remove from the deck.")
        return

    try:
        result = remove_reaction_from_decks_file(
            decks_path,
            reaction_id=reaction_id_to_remove,
            selected_deck_id=selected_deck.deck_id,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    cached_load_decks.clear()
    st.session_state[level_key] = "success"
    if result.removed_reaction:
        st.session_state[message_key] = (
            f"Removed {reaction_id_to_remove} from '{result.deck.name}'."
        )
    else:
        st.session_state[level_key] = "info"
        st.session_state[message_key] = (
            f"{reaction_id_to_remove} is not currently stored in '{result.deck.name}'."
        )
    st.rerun()


def render_decks(records: list[ReactionRecord], decks: list[DeckRecord], decks_path: Path) -> None:
    st.subheader("Decks")
    st.caption("Inspect saved decks, select reactions from them, and remove the selected reaction when needed.")

    if not decks:
        st.info("No decks are available yet. Add reactions to a deck from Browser mode first.")
        return

    message_key = "decks_tab_inspector_message"
    level_key = "decks_tab_inspector_level"

    deck_action_message = st.session_state.pop(message_key, None)
    deck_action_level = st.session_state.pop(level_key, "success")
    if deck_action_message:
        if deck_action_level == "warning":
            st.warning(deck_action_message)
        elif deck_action_level == "info":
            st.info(deck_action_message)
        else:
            st.success(deck_action_message)

    deck_options = [""] + [deck.deck_id for deck in decks]
    deck_labels = {"": "Choose a deck to inspect"}
    deck_labels.update({deck.deck_id: deck.name for deck in decks})

    selected_deck_id = st.selectbox(
        "Deck",
        deck_options,
        format_func=lambda deck_id: deck_labels[deck_id],
        key="decks_tab_selected_deck_id",
    )

    if not selected_deck_id:
        st.caption("Choose a deck to inspect its contents.")
        return

    selected_deck = next((deck for deck in decks if deck.deck_id == selected_deck_id), None)
    if selected_deck is None:
        st.warning("Could not find the selected deck.")
        return

    resolution = resolve_deck_records(selected_deck, build_reaction_lookup(records))

    st.caption(
        f"Deck: {selected_deck.name} | Stored IDs: {len(selected_deck.reaction_ids)} | "
        f"Resolved records: {len(resolution.records)}"
    )
    if selected_deck.description:
        st.write(selected_deck.description)

    if resolution.missing_reaction_ids:
        st.warning(
            "This deck contains missing reaction IDs: "
            + ", ".join(resolution.missing_reaction_ids[:5])
            + (" ..." if len(resolution.missing_reaction_ids) > 5 else "")
        )

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Deck Reactions")
        if resolution.records:
            table = records_to_table(resolution.records)
            previous_selected_id = st.session_state.get("decks_tab_selected_reaction_id")
            table_event = st.dataframe(
                table,
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="decks_tab_results_table",
            )
            selected_rows = list(table_event.selection.rows)
            selected_record = choose_selected_record(
                resolution.records,
                selected_rows=selected_rows,
                previous_reaction_id=previous_selected_id,
            )
            if selected_record is not None:
                st.session_state.decks_tab_selected_reaction_id = selected_record.reaction_id
        else:
            selected_record = None
            st.info("This deck currently has no resolved reactions to show.")

    with right:
        if selected_record is not None:
            render_reaction_core_detail(selected_record)
            if st.button("Remove selected reaction from deck", key=f"decks_tab_remove_{selected_record.reaction_id}"):
                try:
                    result = remove_reaction_from_decks_file(
                        decks_path,
                        reaction_id=selected_record.reaction_id,
                        selected_deck_id=selected_deck.deck_id,
                    )
                except ValueError as exc:
                    st.warning(str(exc))
                    return

                cached_load_decks.clear()
                st.session_state[level_key] = "success"
                if result.removed_reaction:
                    st.session_state[message_key] = (
                        f"Removed {selected_record.reaction_id} from '{result.deck.name}'."
                    )
                else:
                    st.session_state[level_key] = "info"
                    st.session_state[message_key] = (
                        f"{selected_record.reaction_id} is not currently stored in '{result.deck.name}'."
                    )
                st.rerun()

        elif resolution.records:
            st.info("Select a reaction from the deck list to see its details.")


def render_add_reaction(records: list[ReactionRecord], user_path: Path) -> None:
    st.subheader("Add Reaction")
    st.caption("Create a minimal user reaction by entering reaction SMILES.")

    creation_message = st.session_state.pop("add_reaction_message", None)
    creation_level = st.session_state.pop("add_reaction_level", "success")
    if creation_message:
        if creation_level == "warning":
            st.warning(creation_message)
        else:
            st.success(creation_message)

    with st.form("add_user_reaction"):
        reaction_smiles = st.text_input(
            "Reaction SMILES",
            value="",
            placeholder="Example: CCO>>CC=O",
        )
        display_name = st.text_input(
            "Display name (optional)",
            value="",
            placeholder="Optional user-authored name",
        )
        tags_text = st.text_input(
            "Tags (optional, comma-separated)",
            value="",
            placeholder="example: practice, named reaction, chapter 3",
        )
        submitted = st.form_submit_button("Save user reaction")

    if not submitted:
        return

    try:
        new_record = append_user_reaction(
            user_path=user_path,
            reaction_smiles=reaction_smiles,
            existing_records=records,
            display_name=display_name,
            raw_tags=tags_text,
            created_by="streamlit_app",
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    cached_load_reactions.clear()
    st.session_state.add_reaction_level = "success"
    st.session_state.add_reaction_message = f"Saved user reaction {new_record.reaction_id}."
    st.rerun()


def render_reaction_detail(
    record: ReactionRecord,
    all_records: list[ReactionRecord],
    decks: list[DeckRecord],
    decks_path: Path,
    user_path: Path,
) -> None:
    render_reaction_core_detail(record)

    if record.source == "user":
        with st.expander("Edit Reaction", expanded=False):
            render_user_reaction_edit_panel(record, user_path)

    with st.expander("Add To Deck", expanded=False):
        render_deck_action_panel(record, decks, decks_path)

    with st.expander("Inspect Deck", expanded=False):
        render_deck_inspector_panel(
            all_records,
            decks,
            decks_path,
            title="Inspect Deck",
            selectbox_label="Deck to inspect",
            empty_selection_caption="Choose a deck to inspect its contents.",
            remove_button_label="Remove selected reaction from deck",
            state_prefix="browser_deck_inspector",
        )


def find_record_by_id(records: list[ReactionRecord], reaction_id: str | None) -> ReactionRecord | None:
    if reaction_id is None:
        return None

    for record in records:
        if record.reaction_id == reaction_id:
            return record
    return None


def get_current_browser_filters() -> BrowserFilters:
    return BrowserFilters(
        search_text=st.session_state.get("browser_search_text", ""),
        max_reactants=st.session_state.get("browser_max_reactants", 3),
        source=st.session_state.get("browser_source_filter", "all"),
    )


def resolve_selected_deck(
    decks: list[DeckRecord],
    reaction_lookup: dict[str, ReactionRecord],
) -> tuple[DeckRecord | None, list[ReactionRecord], list[str]]:
    selected_deck_id = st.session_state.get("quiz_selected_deck_id", "")
    if not selected_deck_id:
        return None, [], []

    selected_deck = next((deck for deck in decks if deck.deck_id == selected_deck_id), None)
    if selected_deck is None:
        return None, [], []

    resolution = resolve_deck_records(selected_deck, reaction_lookup)
    return selected_deck, resolution.records, resolution.missing_reaction_ids


def start_next_quiz_reaction(records: list[ReactionRecord]) -> None:
    current_id = st.session_state.get("quiz_reaction_id")
    recent_ids = st.session_state.get("quiz_recent_reaction_ids", [])
    record = choose_random_reaction(records, previous_reaction_id=current_id, recent_reaction_ids=recent_ids)
    st.session_state.quiz_reaction_id = record.reaction_id
    st.session_state.quiz_recent_reaction_ids = update_recent_history(
        recent_ids,
        record.reaction_id,
        max_length=recent_history_limit(len(records)),
    )
    st.session_state.quiz_revealed = False


def ensure_quiz_state(records: list[ReactionRecord]) -> None:
    st.session_state.setdefault("quiz_correct", 0)
    st.session_state.setdefault("quiz_incorrect", 0)
    st.session_state.setdefault("quiz_revealed", False)
    st.session_state.setdefault("quiz_last_result", None)
    st.session_state.setdefault("quiz_recent_reaction_ids", [])

    if find_record_by_id(records, st.session_state.get("quiz_reaction_id")) is None:
        start_next_quiz_reaction(records)


def reset_quiz_session(records: list[ReactionRecord]) -> None:
    st.session_state.quiz_correct = 0
    st.session_state.quiz_incorrect = 0
    st.session_state.quiz_revealed = False
    st.session_state.quiz_last_result = None
    st.session_state.quiz_recent_reaction_ids = []
    st.session_state.quiz_reaction_id = None

    if records:
        start_next_quiz_reaction(records)


def record_quiz_result(is_correct: bool) -> None:
    if is_correct:
        st.session_state.quiz_correct += 1
        st.session_state.quiz_last_result = "Marked correct"
    else:
        st.session_state.quiz_incorrect += 1
        st.session_state.quiz_last_result = "Marked incorrect"


def render_quiz(records: list[ReactionRecord], decks: list[DeckRecord]) -> None:
    st.subheader("Quiz")
    st.caption("Prompt: reactants only. Reveal the products when you are ready.")

    if not records:
        st.warning("No reactions are available for quiz mode.")
        return

    deck_options = [""] + [deck.deck_id for deck in decks]
    deck_labels = {"": "All reactions"}
    deck_labels.update({deck.deck_id: deck.name for deck in decks})

    selected_deck_id = st.selectbox(
        "Quiz deck",
        deck_options,
        format_func=lambda deck_id: deck_labels[deck_id],
        key="quiz_selected_deck_id",
    )
    use_browser_subset = st.toggle(
        "Use Browser subset for quiz",
        value=False,
        key="quiz_use_browser_subset",
    )
    browser_subset_records = filter_reactions(records, get_current_browser_filters())
    reaction_lookup = build_reaction_lookup(records)
    selected_deck, deck_records, missing_deck_ids = resolve_selected_deck(decks, reaction_lookup)
    source_pool = choose_quiz_source_pool(
        records,
        deck_records=deck_records if selected_deck is not None else None,
        deck_name=selected_deck.name if selected_deck is not None else None,
        browser_subset_records=browser_subset_records,
        use_browser_subset=use_browser_subset,
    )
    source_records = source_pool.records

    max_quiz_reactants = max(len(record.reactants_smiles) for record in source_records or records)
    default_max_quiz_reactants = min(3, max_quiz_reactants)

    with st.expander("Quiz settings", expanded=False):
        quiz_max_reactants = st.slider(
            "Quiz maximum reactant components",
            min_value=1,
            max_value=max_quiz_reactants,
            value=default_max_quiz_reactants,
            key="quiz_max_reactants",
        )
        quiz_require_single_product = st.toggle(
            "Require exactly 1 product",
            value=False,
            key="quiz_require_single_product",
        )
        if st.button("Reset quiz session"):
            filtered_records = filter_quiz_records(
                source_records,
                QuizFilters(
                    max_reactants=quiz_max_reactants,
                    require_single_product=quiz_require_single_product,
                ),
            )
            reset_quiz_session(filtered_records)
            st.rerun()

    filtered_records = filter_quiz_records(
        source_records,
        QuizFilters(
            max_reactants=quiz_max_reactants,
            require_single_product=quiz_require_single_product,
        ),
    )

    st.caption(
        f"Quiz source: {source_pool.label} ({len(source_records)} reaction(s)) | "
        f"Quiz pool: {len(filtered_records)} reaction(s) | "
        f"Max reactants: {quiz_max_reactants} | "
        f"Single product only: {'on' if quiz_require_single_product else 'off'}"
    )

    if missing_deck_ids:
        st.warning(
            "Selected deck contains missing reaction IDs: "
            + ", ".join(missing_deck_ids[:5])
            + (" ..." if len(missing_deck_ids) > 5 else "")
        )

    if not filtered_records:
        if selected_deck is not None and not deck_records and missing_deck_ids:
            st.warning("The selected deck does not resolve to any reactions in the loaded dataset.")
        elif use_browser_subset and not source_records:
            st.warning("The current Browser subset is empty. Adjust Browser filters or turn off Browser subset mode.")
        else:
            st.warning("No reactions match the current quiz filters.")
        return

    ensure_quiz_state(filtered_records)
    record = find_record_by_id(filtered_records, st.session_state.quiz_reaction_id)
    if record is None:
        st.warning("Could not find the current quiz reaction.")
        return

    answered = st.session_state.quiz_correct + st.session_state.quiz_incorrect
    st.write(
        f"Answered: {answered} | Correct: {st.session_state.quiz_correct} | "
        f"Incorrect: {st.session_state.quiz_incorrect}"
    )

    render_molecule_grid("Reactants", record.reactants_smiles)

    col_reveal, col_next = st.columns(2)
    with col_reveal:
        if st.button("Reveal answer", disabled=st.session_state.quiz_revealed):
            st.session_state.quiz_revealed = True
            st.rerun()
    with col_next:
        if st.button("Next reaction"):
            st.session_state.quiz_last_result = None
            start_next_quiz_reaction(filtered_records)
            st.rerun()

    if not st.session_state.quiz_revealed:
        st.info("Think of the product, then reveal the answer.")
        return

    render_molecule_grid("Products", record.products_smiles)

    st.subheader("Reaction SMILES")
    st.code(record.reaction_smiles, language="text")

    col_correct, col_incorrect = st.columns(2)
    with col_correct:
        if st.button("Mark correct"):
            record_quiz_result(True)
            start_next_quiz_reaction(filtered_records)
            st.rerun()
    with col_incorrect:
        if st.button("Mark incorrect"):
            record_quiz_result(False)
            start_next_quiz_reaction(filtered_records)
            st.rerun()

    if st.session_state.quiz_last_result:
        st.caption(st.session_state.quiz_last_result)


def render_browser(
    records: list[ReactionRecord],
    decks: list[DeckRecord],
    decks_path: Path,
    user_path: Path,
) -> None:
    with st.sidebar:
        st.header("Filters")
        search_text = st.text_input("Search reaction ID or SMILES", "", key="browser_search_text")
        source_filter = st.selectbox(
            "Reaction source",
            ["all", "base", "user"],
            format_func=lambda value: {"all": "All", "base": "Base", "user": "User"}[value],
            key="browser_source_filter",
        )
        max_reactants = st.slider(
            "Maximum reactant components",
            min_value=1,
            max_value=3,
            value=3,
            key="browser_max_reactants",
        )
        max_results = st.slider(
            "Rows shown in table",
            min_value=25,
            max_value=500,
            value=100,
            step=25,
            key="browser_max_results",
        )

    filtered_records = filter_reactions(
        records,
        BrowserFilters(search_text=search_text, max_reactants=max_reactants, source=source_filter),
    )
    table = records_to_table(filtered_records[:max_results])

    source_label = {"all": "all", "base": "base", "user": "user"}[source_filter]
    st.write(
        f"Showing {len(table)} of {len(filtered_records)} matching reactions from {len(records)} loaded records "
        f"(source filter: {source_label})."
    )

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Reactions")
        selected_record = None
        if filtered_records:
            previous_selected_id = st.session_state.get("browser_selected_reaction_id")
            table_event = st.dataframe(
                table,
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="browser_results_table",
            )
            selected_rows = list(table_event.selection.rows)
            selected_record = choose_selected_record(
                filtered_records[:max_results],
                selected_rows=selected_rows,
                previous_reaction_id=previous_selected_id,
            )
            if selected_record is not None:
                st.session_state.browser_selected_reaction_id = selected_record.reaction_id
        else:
            st.warning("No reactions match the current filters.")

    with right:
        if selected_record is not None:
            render_reaction_detail(selected_record, records, decks, decks_path, user_path)


def main() -> None:
    st.set_page_config(page_title="PPChem Reaction Browser", layout="wide")

    st.title("PPChem")
    st.caption("Browse and quiz reactions from the conservative MVP dataset.")

    if not DATASET_PATH.exists():
        st.error(f"Dataset not found: {DATASET_PATH}")
        st.stop()

    records = cached_load_reactions(str(DATASET_PATH), str(USER_DATASET_PATH))
    decks = cached_load_decks(str(DECKS_PATH)) if DECKS_PATH.exists() else []

    browser_tab, quiz_tab, decks_tab, add_reaction_tab = st.tabs(["Browser", "Quiz", "Decks", "Add Reaction"])
    with browser_tab:
        render_browser(records, decks, DECKS_PATH, USER_DATASET_PATH)
    with quiz_tab:
        render_quiz(records, decks)
    with decks_tab:
        render_decks(records, decks, DECKS_PATH)
    with add_reaction_tab:
        render_add_reaction(records, USER_DATASET_PATH)


if __name__ == "__main__":
    main()
