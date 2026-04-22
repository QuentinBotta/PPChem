from pathlib import Path

from ppchem.decks.deck_io import read_deck_records
from ppchem.decks.deck_resolution import build_reaction_lookup, resolve_deck_records
from ppchem.models.reaction_io import read_reaction_records


def test_sample_decks_load_and_resolve_against_mvp_dataset() -> None:
    project_root = Path(__file__).resolve().parents[1]
    decks = read_deck_records(project_root / "data" / "decks" / "sample_decks.json")
    records = read_reaction_records(project_root / "data" / "processed" / "reactions.mvp.json")
    lookup = build_reaction_lookup(records)

    assert len(decks) >= 1

    for deck in decks:
        resolution = resolve_deck_records(deck, lookup)
        assert resolution.records
        assert resolution.missing_reaction_ids == []
