# PPChem Data Layer and MVP Browser

This repository currently implements the **foundation, conversion pipeline, MVP filtering, first reaction browser scaffold, and simple quiz mode**.
It does **not** include advanced spaced repetition or user-input UI yet.

## What is implemented
- Internal reaction schema (`ReactionRecord`) with JSON serialization helpers.
- CSV importer/converter for `tpl.csv`-style data using pandas.
- Conservative MVP subset filtering for the first app dataset.
- First Streamlit reaction browser and quiz mode using `data/processed/reactions.mvp.json`.
- Conservative validation with RDKit when available.
- Explicit skip/report behavior for problematic rows.
- Basic automated tests.

## Project structure
- `src/ppchem/models/` -> schema and JSON read/write helpers.
- `src/ppchem/importers/` -> dataset conversion (`tpl_importer.py`).
- `src/ppchem/curation/` -> conservative MVP dataset filtering.
- `src/ppchem/app/` -> helper functions used by the Streamlit app.
- `scripts/convert_tpl.py` -> CLI wrapper for conversion.
- `scripts/filter_mvp.py` -> CLI wrapper for creating `reactions.mvp.json`.
- `app/streamlit_app.py` -> first Streamlit reaction browser and quiz mode.
- `tests/` -> schema, importer, curation, and app helper tests.
- `data/raw/` -> input CSV files.
- `data/processed/` -> generated JSON outputs and reports.


## Usage

### 1) Quick sample conversion
```bash
PYTHONPATH=src python scripts/convert_tpl.py --input data/raw/tpl_sample.csv --output data/processed/reactions.sample.json --report data/processed/import_report.sample.json
```

### 2) Full conversion (when `data/raw/tpl.csv` is available)
```bash
PYTHONPATH=src python scripts/convert_tpl.py --input data/raw/tpl.csv --output data/processed/reactions.base.json --report data/processed/import_report.json
```

### 3) Create the MVP app dataset
```bash
PYTHONPATH=src python scripts/filter_mvp.py --input data/processed/reactions.base.json --output data/processed/reactions.mvp.json --report data/processed/filter_report.json
```

### 4) Run the Streamlit reaction browser
Install the app dependency if needed:
```bash
pip install ".[app]"
```

To enable molecule and reaction rendering in Browser and Quiz, install the optional RDKit support too:
```bash
pip install ".[app-chem]"
```

For a student project on Windows, the most reliable path is usually a dedicated conda environment instead of reusing `base`.
Example:
```powershell
conda create -n ppchem-rdkit python=3.13 -y
conda activate ppchem-rdkit
pip install -e ".[app-chem]"
```

Then run:
```bash
PYTHONPATH=src python -m streamlit run app/streamlit_app.py
```

On Windows PowerShell, use:
```powershell
$env:PYTHONPATH="src"
python -m streamlit run app/streamlit_app.py
```

You can quickly verify RDKit is available before launching the app:
```powershell
python -c "from rdkit import Chem; from rdkit.Chem import Draw, rdChemReactions; print('RDKit OK')"
```

If that command fails, the app will still run but will fall back to SMILES text rendering.

## Notes on metadata policy
The converter, MVP filter, and app do **not** invent chemistry metadata. If fields such as reaction name/class/hint/difficulty are not provided, they remain null/empty. The app falls back to `reaction_id` when `display_name` is unavailable.

## Notes on deck references
Persistent decks reference reactions by `reaction_id`. That works well as long as imported reactions keep stable IDs across rebuilds of the processed dataset. In the current importer, stability is strongest when the input dataset provides a stable row identifier; if import falls back to CSV row index, deck references depend on row order staying unchanged.

## Running tests
```bash
PYTHONPATH=src pytest
```
