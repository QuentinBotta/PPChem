from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MoleculeGridRenderResult:
    image: Any | None
    fallback_smiles: list[str]
    used_rdkit: bool


@dataclass(frozen=True)
class ReactionRenderResult:
    image: Any | None
    fallback_reason: str | None
    used_rdkit: bool


def build_molecule_grid_image(
    smiles_values: list[str],
    *,
    chem_module: Any,
    draw_module: Any,
) -> MoleculeGridRenderResult:
    if chem_module is None or draw_module is None:
        return MoleculeGridRenderResult(image=None, fallback_smiles=list(smiles_values), used_rdkit=False)

    molecules = []
    captions = []
    fallback_smiles: list[str] = []

    for smiles in smiles_values:
        try:
            molecule = chem_module.MolFromSmiles(smiles)
        except Exception:
            molecule = None

        if molecule is None:
            fallback_smiles.append(smiles)
            continue

        molecules.append(molecule)
        captions.append(smiles)

    if not molecules:
        return MoleculeGridRenderResult(
            image=None,
            fallback_smiles=fallback_smiles or list(smiles_values),
            used_rdkit=False,
        )

    try:
        image = draw_module.MolsToGridImage(
            molecules,
            molsPerRow=2,
            subImgSize=(280, 180),
            legends=captions,
        )
    except Exception:
        return MoleculeGridRenderResult(image=None, fallback_smiles=list(smiles_values), used_rdkit=False)

    return MoleculeGridRenderResult(image=image, fallback_smiles=fallback_smiles, used_rdkit=True)


def build_reaction_image(
    reaction_smiles: str,
    *,
    reaction_module: Any,
    draw_module: Any,
) -> ReactionRenderResult:
    if reaction_module is None or draw_module is None:
        return ReactionRenderResult(
            image=None,
            fallback_reason="RDKit is not available, so molecules are shown as SMILES text.",
            used_rdkit=False,
        )

    try:
        reaction = reaction_module.ReactionFromSmarts(reaction_smiles, useSmiles=True)
    except Exception:
        reaction = None

    if reaction is None:
        return ReactionRenderResult(
            image=None,
            fallback_reason="RDKit could not render this reaction. Showing SMILES text instead.",
            used_rdkit=False,
        )

    try:
        image = draw_module.ReactionToImage(reaction, subImgSize=(320, 180))
    except Exception:
        return ReactionRenderResult(
            image=None,
            fallback_reason="RDKit could not render this reaction. Showing SMILES text instead.",
            used_rdkit=False,
        )

    return ReactionRenderResult(image=image, fallback_reason=None, used_rdkit=True)
