import json
from pathlib import Path

from ppchem.curation.mvp_filter import MvpFilterCriteria, filter_mvp_reactions
from ppchem.models.reaction_io import write_reaction_records
from ppchem.models.reaction_schema import ReactionRecord


def _record(reaction_id: str, reaction_smiles: str, reactants: list[str], products: list[str]) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        source="base",
        created_by="test",
        created_at="2026-04-14T00:00:00Z",
        reaction_smiles=reaction_smiles,
        reactants_smiles=reactants,
        products_smiles=products,
        quality={"is_validated": False, "validation_messages": []},
        provenance={"dataset": "test", "dataset_record_id": reaction_id, "import_version": "0.1"},
    )


def test_filter_keeps_simple_records_and_reports_reasons(tmp_path: Path) -> None:
    input_path = tmp_path / "base.json"
    output_path = tmp_path / "mvp.json"
    report_path = tmp_path / "report.json"
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("base_2", "CC.CC.CC.CC>>CCCC", ["CC", "CC", "CC", "CC"], ["CCCC"]),
        _record("base_3", "CCCCCCCCCCCC>>CC", ["CCCCCCCCCCCC"], ["CC"]),
    ]
    write_reaction_records(records, input_path)

    criteria = MvpFilterCriteria(
        max_records=10,
        max_reaction_smiles_length=10,
        max_reactants=3,
        required_product_count=1,
        max_component_smiles_length=20,
    )
    report = filter_mvp_reactions(input_path, output_path, report_path=report_path, criteria=criteria)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["reaction_id"] for record in payload] == ["base_1"]
    assert report["total_input_rows"] == 3
    assert report["total_kept_rows"] == 1
    assert report["total_filtered_rows"] == 2
    assert report["filter_reason_counts"]["too_many_reactants"] == 1
    assert report["filter_reason_counts"]["reaction_smiles_too_long"] == 2
    assert json.loads(report_path.read_text(encoding="utf-8"))["total_kept_rows"] == 1


def test_filter_reports_mvp_size_limit(tmp_path: Path) -> None:
    input_path = tmp_path / "base.json"
    output_path = tmp_path / "mvp.json"
    records = [
        _record("base_1", "CCO>>CC=O", ["CCO"], ["CC=O"]),
        _record("base_2", "CCN>>CC=N", ["CCN"], ["CC=N"]),
    ]
    write_reaction_records(records, input_path)

    report = filter_mvp_reactions(input_path, output_path, criteria=MvpFilterCriteria(max_records=1))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["reaction_id"] for record in payload] == ["base_1"]
    assert report["filter_reason_counts"]["mvp_size_limit"] == 1

