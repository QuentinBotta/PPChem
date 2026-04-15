import json
from pathlib import Path

from ppchem.importers.tpl_importer import convert_tpl_csv


def test_converter_handles_valid_and_problematic_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "id,reaction_smiles\n"
        "1,CCO>>CC=O\n"
        "2,\n"
        "3,not_a_reaction\n",
        encoding="utf-8",
    )

    out_json = tmp_path / "out.json"
    out_report = tmp_path / "report.json"

    report = convert_tpl_csv(csv_path, out_json, report_path=out_report)

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["reaction_id"] == "base_1"
    assert payload[0]["display_name"] is None
    assert payload[0]["reaction_class"] is None
    assert payload[0]["difficulty"] is None
    assert payload[0]["hint"] is None

    assert report["row_count_input"] == 3
    assert report["row_count_output"] == 1
    assert report["row_count_skipped"] == 2


def test_converter_detects_reaction_column_alias(tmp_path: Path) -> None:
    csv_path = tmp_path / "input_alias.csv"
    csv_path.write_text("id,rxn\n10,CC>>CO\n", encoding="utf-8")

    out_json = tmp_path / "out.json"
    report = convert_tpl_csv(csv_path, out_json)

    assert report["reaction_column_used"] == "rxn"
