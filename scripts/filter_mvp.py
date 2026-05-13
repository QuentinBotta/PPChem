#!/usr/bin/env python3
"""CLI wrapper for building the conservative MVP reaction subset."""

from __future__ import annotations

import argparse
import json

from ppchem.curation.mvp_filter import MvpFilterCriteria, filter_mvp_reactions


def main() -> None:
    """Parse CLI arguments, apply the MVP filter, and print the report JSON."""
    parser = argparse.ArgumentParser(description="Create a conservative MVP reaction subset")
    parser.add_argument("--input", default="data/processed/reactions.base.json", help="Path to input JSON")
    parser.add_argument("--output", default="data/processed/reactions.mvp.json", help="Path to output JSON")
    parser.add_argument("--report", default="data/processed/filter_report.json", help="Path to report JSON")
    parser.add_argument("--max-records", type=int, default=5000, help="Maximum records to keep")
    parser.add_argument("--max-length", type=int, default=120, help="Maximum reaction SMILES length")
    parser.add_argument("--max-reactants", type=int, default=3, help="Maximum reactant components")
    parser.add_argument("--product-count", type=int, default=1, help="Required product component count")
    parser.add_argument("--max-component-length", type=int, default=80, help="Maximum single component SMILES length")
    args = parser.parse_args()

    criteria = MvpFilterCriteria(
        max_records=args.max_records,
        max_reaction_smiles_length=args.max_length,
        max_reactants=args.max_reactants,
        required_product_count=args.product_count,
        max_component_smiles_length=args.max_component_length,
    )
    report = filter_mvp_reactions(args.input, args.output, report_path=args.report, criteria=criteria)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
