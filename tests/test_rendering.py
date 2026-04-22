from ppchem.app.rendering import build_molecule_grid_image, build_reaction_image


class FakeChemModule:
    @staticmethod
    def MolFromSmiles(smiles: str) -> object | None:
        if smiles == "bad":
            return None
        if smiles == "boom":
            raise ValueError("parse error")
        return {"smiles": smiles}


class FakeDrawModule:
    @staticmethod
    def MolsToGridImage(molecules: list[object], **_: object) -> str:
        if any(molecule == {"smiles": "explode"} for molecule in molecules):
            raise ValueError("draw error")
        return "molecule-grid"

    @staticmethod
    def ReactionToImage(reaction: object, **_: object) -> str:
        if reaction == "explode":
            raise ValueError("draw error")
        return "reaction-image"


class FakeReactionModule:
    @staticmethod
    def ReactionFromSmarts(reaction_smiles: str, *, useSmiles: bool) -> object | None:
        assert useSmiles is True
        if reaction_smiles == "bad":
            return None
        if reaction_smiles == "boom":
            raise ValueError("parse error")
        if reaction_smiles == "explode":
            return "explode"
        return {"reaction_smiles": reaction_smiles}


def test_build_molecule_grid_image_uses_rdkit_for_valid_molecules() -> None:
    result = build_molecule_grid_image(["CCO", "CCN"], chem_module=FakeChemModule, draw_module=FakeDrawModule)

    assert result.image == "molecule-grid"
    assert result.fallback_smiles == []
    assert result.used_rdkit is True


def test_build_molecule_grid_image_falls_back_for_invalid_molecules_only() -> None:
    result = build_molecule_grid_image(["CCO", "bad", "boom"], chem_module=FakeChemModule, draw_module=FakeDrawModule)

    assert result.image == "molecule-grid"
    assert result.fallback_smiles == ["bad", "boom"]
    assert result.used_rdkit is True


def test_build_molecule_grid_image_falls_back_to_all_smiles_when_rdkit_draw_fails() -> None:
    result = build_molecule_grid_image(["explode"], chem_module=FakeChemModule, draw_module=FakeDrawModule)

    assert result.image is None
    assert result.fallback_smiles == ["explode"]
    assert result.used_rdkit is False


def test_build_reaction_image_reports_missing_rdkit() -> None:
    result = build_reaction_image("CCO>>CC=O", reaction_module=None, draw_module=None)

    assert result.image is None
    assert result.used_rdkit is False
    assert result.fallback_reason == "RDKit is not available, so molecules are shown as SMILES text."


def test_build_reaction_image_falls_back_when_parsing_fails() -> None:
    result = build_reaction_image("bad", reaction_module=FakeReactionModule, draw_module=FakeDrawModule)

    assert result.image is None
    assert result.used_rdkit is False
    assert result.fallback_reason == "RDKit could not render this reaction. Showing SMILES text instead."


def test_build_reaction_image_falls_back_when_drawing_fails() -> None:
    result = build_reaction_image("explode", reaction_module=FakeReactionModule, draw_module=FakeDrawModule)

    assert result.image is None
    assert result.used_rdkit is False
    assert result.fallback_reason == "RDKit could not render this reaction. Showing SMILES text instead."
