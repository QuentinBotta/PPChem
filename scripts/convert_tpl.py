#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from ppchem.importers.tpl_importer import convert_tpl_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert tpl.csv to PPChem internal JSON format")
    parser.add_argument("--input", default="data/raw/tpl.csv", help="Path to input CSV")
    parser.add_argument("--output", default="data/processed/reactions.base.json", help="Path to output JSON")
    parser.add_argument("--report", default="data/processed/import_report.json", help="Path to report JSON")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional max rows for quick runs")
    args = parser.parse_args()

    report = convert_tpl_csv(args.input, args.output, max_rows=args.max_rows, report_path=args.report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
