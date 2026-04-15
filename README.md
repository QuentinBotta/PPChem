# PPChem Data Layer (Foundation + Converter)

This repository currently implements the **foundation and conversion pipeline only**.
It does **not** include Streamlit UI, quiz logic, or user-input UI yet.

## What is implemented
- Internal reaction schema (`ReactionRecord`) with JSON serialization helpers.
- CSV importer/converter for `tpl.csv`-style data using pandas.
- Conservative validation with RDKit when available.
- Explicit skip/report behavior for problematic rows.
- Basic automated tests.

## Project structure
- `src/ppchem/models/` → schema + JSON read/write helpers.
- `src/ppchem/importers/` → dataset conversion (`tpl_importer.py`).
- `scripts/convert_tpl.py` → CLI wrapper for conversion.
- `tests/` → schema and importer tests.
- `data/raw/` → input CSV files.
- `data/processed/` → generated JSON outputs and import reports.

## Usage

### 1) Quick sample conversion
```bash
PYTHONPATH=src python scripts/convert_tpl.py --input data/raw/tpl_sample.csv --output data/processed/reactions.sample.json --report data/processed/import_report.sample.json
```

### 2) Full conversion (when `data/raw/tpl.csv` is available)
```bash
PYTHONPATH=src python scripts/convert_tpl.py --input data/raw/tpl.csv --output data/processed/reactions.base.json --report data/processed/import_report.json
```

## Notes on metadata policy
The converter does **not** invent chemistry metadata. If fields such as reaction name/class/hint/difficulty are not provided, they remain null/empty.

## Running tests
```bash
PYTHONPATH=src pytest
```
