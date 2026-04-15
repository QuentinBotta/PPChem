# PLAN — Organic Chemistry Reaction Learning App

## 1) Project goal
Build a beginner-friendly Python app for EPFL students to **learn and practice organic reactions** through quiz-style interaction, using a cleaned internal reaction dataset (JSON) rather than raw source files.

## 2) Target users
- Primary: students in **Practical Programming in Chemistry** (limited programming experience).
- Secondary: course staff/demo audience who need a clear, reliable prototype.

## 3) MVP (demo-ready scope)
1. **Data import/conversion pipeline** (standalone script/module):
   - Input: professor-recommended source dataset (`tpl.csv`) and optional small curated overrides.
   - Output: app-ready internal JSON file.
2. **Reaction browser**:
   - List reactions with basic filters (e.g., source/provenance and only metadata that actually exists).
   - Show reactants/products as SMILES and rendered molecule/reaction image.
3. **Quiz mode (core Anki-like loop)**:
   - Prompt with reactant side (or product side), reveal answer, mark confidence/correctness.
   - Simple local progress tracking (JSON).
4. **Manual reaction add (v1)**:
   - Students can add reactions with required SMILES fields.
   - Store user reactions separately from imported base dataset.

## 4) Non-goals for MVP
- Inferring or auto-generating missing chemistry metadata from ambiguous records.
- Full spaced-repetition algorithm optimization.
- Mechanism drawing/editor or stepwise mechanism tutoring.
- Rich catalyst/condition intelligence or automatic retrosynthesis.
- Multi-user cloud backend/account system.

## 5) Proposed tech stack (Python 3.10)
- **App framework:** **Streamlit** (recommended for MVP).
  - Why: fast UI iteration, low boilerplate, course-aligned, easy demo.
  - Tradeoff: limited complex front-end control (acceptable for MVP).
- **Core language:** Python 3.10.
- **Data handling:** **pandas** for CSV ingestion/cleaning/validation in import step.
- **Chemistry toolkit:** **RDKit** for SMILES validation and rendering.
- **Serialization/storage:** JSON files for base data, user data, and progress in v1.
- **Testing/documentation:** `pytest` + lightweight docs (README + module docstrings).

### Is JSON alone enough for first version?
**Yes** for MVP, if data volumes remain modest (course project scale). JSON is human-readable, Git-friendly, and easy for beginners. If scale or concurrent edits become problematic later, move to SQLite while keeping JSON schema compatibility.

## 6) Data workflow (explicit separation)
1. **Source acquisition** (`tpl.csv` and optional manual curation file).
2. **Import/convert script**:
   - Parse source columns with pandas.
   - Normalize fields to internal schema.
   - Validate SMILES/reactions with RDKit where possible.
   - Preserve uncertainty: if values are missing/ambiguous, keep fields empty (`null`, `[]`) or set `"unknown"` where applicable.
   - Do **not** invent reaction names/classes/hints/difficulty labels.
3. **Internal dataset output** (`data/processed/reactions.base.json`).
4. **App runtime loading**:
   - Load base reactions + user-added reactions.
   - Merge in-memory with provenance tags (`source=base|user`).
5. **User actions**:
   - Quiz results written to `progress.json`.
   - New user reactions written to `reactions.user.json`.

> Important architectural rule: app code must never depend directly on raw source dataset format.

## 7) Internal JSON schema (student-facing, one reaction entry)

```json
{
  "reaction_id": "base_000123",
  "source": "base",
  "created_by": "import_script",
  "created_at": "2026-04-14T00:00:00Z",

  "reaction_smiles": "CCO.O=C=O>>CCOC(=O)O",
  "reactants_smiles": ["CCO", "O=C=O"],
  "products_smiles": ["CCOC(=O)O"],

  "display_name": null,
  "reaction_class": null,
  "tags": [],
  "difficulty": null,
  "hint": null,
  "notes": null,

  "quality": {
    "is_validated": true,
    "validation_messages": []
  },

  "provenance": {
    "dataset": "drfp_tpl",
    "dataset_record_id": "tpl_row_123",
    "import_version": "0.1.0"
  },

  "extensions": {
    "conditions": null,
    "catalyst": null,
    "mechanism": null,
    "references": []
  }
}
```

### Field policy for MVP
- **Required for MVP**
  - `reaction_id`, `source`, `reaction_smiles`
  - `reactants_smiles`, `products_smiles`
  - `quality`, `provenance`
- **Optional but empty/null by default in imported data**
  - `display_name`, `reaction_class`, `tags`, `difficulty`, `hint`, `notes`
  - `extensions.*`
- **Intended for later manual enrichment (not auto-inferred in MVP)**
  - Human-readable reaction naming/classification
  - Pedagogical metadata (difficulty/hints/notes)
  - Additional chemistry metadata (conditions/catalyst/mechanism/references)

### Quiz/session data is separate from reaction data
- Fields like `prompt_side`, quiz outcomes, and scheduling are **not** stored in the core reaction record.
- They belong in quiz/session/progress files (e.g., `progress.json`) and app logic.

## 8) Suggested folder structure

```text
PPChem/
  PLAN.md
  README.md
  pyproject.toml

  data/
    raw/                    # source files (e.g., tpl.csv)
    processed/              # generated app-ready JSON
      reactions.base.json
    user/                   # user-generated data (never overwrite)
      reactions.user.json
      progress.json

  src/
    ppchem/
      __init__.py

      importers/            # dataset import/conversion only
        tpl_importer.py
        normalize.py
        validate.py

      models/               # core data model / schema helpers
        reaction_schema.py
        reaction_io.py

      app/                  # Streamlit UI and app logic
        streamlit_app.py
        browser_view.py
        quiz_view.py
        add_reaction_view.py

      services/             # non-UI logic
        quiz_engine.py
        filtering.py
        rendering.py

      extensions/           # reserved for future advanced chemistry features
        README.md

  tests/
    test_importer.py
    test_schema.py
    test_quiz_engine.py
```

## 9) Milestone order (realistic)
1. **M1 — Foundation**
   - Repository scaffold, dependency setup, minimal schema object + JSON IO.
2. **M2 — Import pipeline**
   - Implement `tpl.csv` converter to internal JSON with basic validation/logging.
3. **M3 — Data quality pass**
   - Add explicit handling for unknown/ambiguous values (leave empty/null/unknown; no invented metadata).
4. **M4 — Streamlit browser**
   - Load processed JSON, filter/browse entries, render molecules.
5. **M5 — Quiz loop**
   - Prompt/reveal/mark flow with local progress persistence.
6. **M6 — User-added reactions (SMILES v1)**
   - Form input + RDKit validation + append to `reactions.user.json`.
   - Allow optional manual metadata entry, kept empty if not provided.
7. **M7 — Demo polish**
   - Error messages, docs, sample dataset subset, basic tests.

> Implementation can be split into smaller bounded tasks at each milestone (e.g., scaffold/schema/IO first, converter second, app scaffold third).

## 10) Main technical risks and simplifications

### Key risks
- **Dataset pedagogical mismatch:** raw reactions may be noisy/non-teaching-oriented.
- **Chemistry validity issues:** malformed/ambiguous SMILES or reaction strings.
- **Metadata overreach risk:** accidental invention of labels not present in data.
- **Scope creep:** jumping to advanced chemistry features too early.
- **Beginner maintainability:** architecture becoming too complex.

### Keep simple first
- Keep quiz algorithm simple (no advanced scheduling in MVP).
- Use small curated subset first for stable demo quality.
- Keep schema stable and explicit; use `extensions` for future fields.
- Maintain strict boundary: import/cleaning logic separate from app UI.
- Preserve uncertainty rather than guessing chemistry context.

## 11) Uncertainties (explicit)
- Exact column semantics/quality of `tpl.csv` need confirmation during import exploration.
- Some records may not include student-friendly labels.
- RDKit reaction parsing behavior may vary across edge-case entries.

## 12) Immediate next coding step (after plan approval)
Implement M1 + M2 only:
- scaffold project modules,
- create schema + JSON IO,
- build first working `tpl.csv` → `reactions.base.json` converter,
- enforce “no invented metadata” defaults,
- add tests for schema and converter basics.
