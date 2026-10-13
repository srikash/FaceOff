"""Register the subject to the template and warp template images into subject space.

`register` runs antsAI, the affine stage and (optionally) the SyN stages. Callers never see
file names, transform order or ANTs flags: they call `Transforms.to_subject` with a template
image and a `Stage` (`DEFACE` or `REFACE`).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .ants import AntsRunner
from .template import TEMPLATE_BRAIN_MASK, TEMPLATE_REF, TEMPLATE_REFACE_MASK
from .workspace import Workspace


class Stage(Enum):
    DEFACE = "deface"
    REFACE = "reface"


# (SyN gradient step/regularisation, convergence, shrink factors, smoothing sigmas)
_DEFACE_SYN = ("[0.1,3,0]", "[50x25,1e-6,10]", "2x1", "1x0vox")
# The reface SyN stops at half resolution: the full-resolution level took ~75% of its time
# for a negligible gain in face fit (correlation 0.857 -> 0.853 on the test scan).
_REFACE_SYN = ("[0.2,3,0]", "[100x100x70x50,1e-6,10]", "10x6x4x2", "5x3x2x1vox")

_AFFINE_PREFIX = "affine_"
_SYN_PREFIX = "syn_"
_FACE_PREFIX = "face_"


class Transforms:
    """The registration results for one subject, in a scratch workspace."""

    def __init__(
        self, ants: AntsRunner, ws: Workspace, subject: Path, syn: bool, reface: bool
    ) -> None:
        self._ants = ants
        self._ws = ws
        self._subject = subject
        self._syn = syn
        self._reface = reface

    @property
    def affine(self) -> Path:
        """Subject -> template affine (what the reorientation is derived from)."""
        return self._ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")

    def to_subject(
        self,
        template_image: Path,
        output: Path,
        stage: Stage,
        interpolation: str = "GenericLabel",
        reference: Path | None = None,
    ) -> None:
        """Warp a template-space image into subject space with this stage's transforms, onto
        the subject's grid or onto `reference` (a 3D image in the same scanner space)."""
        self._ants.run("antsApplyTransforms", [
            "--dimensionality", "3",
            "--interpolation", interpolation,
            "--reference-image", reference or self._subject,
            "--input", template_image,
            "--output", output,
            "--verbose", "0",
            *self._inverse_chain(stage),
        ])

    def _inverse_chain(self, stage: Stage) -> list[str]:
        # Order matters: inverses of the earlier transforms come first, the inverse of the
        # last-fitted warp last. The reverse order silently gives wrong output.
        affine_inverse = ["--transform", f"[{self.affine},1]"]
        syn_inverse = ["--transform", str(self._ws.path(f"{_SYN_PREFIX}InverseComposite.h5"))]
        if stage is Stage.DEFACE:
            return syn_inverse if self._syn else affine_inverse
        if not self._reface:
            raise ValueError("No reface registration was run.")
        # With a --syn warp as the starting point, the face warp is the second warp.
        if self._syn:
            warp = self._ws.path(f"{_FACE_PREFIX}2InverseWarp.nii.gz")
            return [*syn_inverse, "--transform", str(warp)]
        warp = self._ws.path(f"{_FACE_PREFIX}1InverseWarp.nii.gz")
        return [*affine_inverse, "--transform", str(warp)]


def register(
    ants: AntsRunner, ws: Workspace, subject: Path, *, syn: bool, reface: bool
) -> Transforms:
    """Centre-of-mass init, rigid + affine, then SyN as requested (see Transforms)."""
    init = ws.path("init.mat")
    ants.run("antsAI", [
        "--dimensionality", "3",
        "--random-seed", "13",
        "--transform", "AlignCentersOfMass",
        "--masks", TEMPLATE_BRAIN_MASK,
        "--metric", f"MI[{TEMPLATE_REF},{subject},32,Regular,0.25]",
        "--output", init,
    ])
    ants.run("antsRegistration", _affine_args(subject, init, ws.path(_AFFINE_PREFIX)))
    affine = ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")

    # SyN stages are separate calls. The deface SyN (--syn) is not required (the affine alone
    # already gives the deface mask) and is kept for completeness; it starts from the affine
    # and is guided by the brain mask; the reface SyN starts from that warp (or the affine) and is
    # fitted over the reface mask.
    if syn:
        ants.run("antsRegistration", _syn_args(
            subject, affine, TEMPLATE_BRAIN_MASK, ws.path(_SYN_PREFIX), _DEFACE_SYN,
            write_composite=True,
        ))
    if reface:
        start = ws.path(f"{_SYN_PREFIX}Composite.h5") if syn else affine
        ants.run("antsRegistration", _syn_args(
            subject, start, TEMPLATE_REFACE_MASK, ws.path(_FACE_PREFIX), _REFACE_SYN,
        ))
    return Transforms(ants, ws, subject, syn, reface)


def _affine_args(subject: Path, init: Path, prefix: Path) -> list[str | Path]:
    brain_mask = f"[{TEMPLATE_BRAIN_MASK},1]"
    mi = f"MI[{TEMPLATE_REF},{subject},1,32,Regular,0.25]"
    stage = ["--metric", mi, "--convergence", "[1000x500x250x100,1e-6,10]",
             "--shrink-factors", "12x8x4x2", "--smoothing-sigmas", "4x3x2x1vox"]
    return [
        "--verbose", "0",
        "--random-seed", "13",
        "--dimensionality", "3",
        "--float", "1",
        "--collapse-output-transforms", "1",
        "--output", prefix,  # transforms only: no warped images
        "--use-histogram-matching", "0",
        "--winsorize-image-intensities", "[0.005,0.995]",
        "--initial-moving-transform", init,
        "--masks", brain_mask, "--transform", "Rigid[0.1]", *stage,
        "--masks", brain_mask, "--transform", "Affine[0.1]", *stage,
    ]


def _syn_args(
    subject: Path,
    init: Path,
    mask: Path,
    prefix: Path,
    schedule: tuple[str, str, str, str],
    write_composite: bool = False,
) -> list[str | Path]:
    step, convergence, shrink, smoothing = schedule
    return [
        "--verbose", "0",
        "--random-seed", "13",
        "--dimensionality", "3",
        "--float", "1",
        "--collapse-output-transforms", "1",
        "--write-composite-transform", "1" if write_composite else "0",
        "--output", prefix,  # transforms only: no warped images
        "--use-histogram-matching", "0",
        "--winsorize-image-intensities", "[0.005,0.995]",
        "--masks", f"[{mask},1]",
        "--initial-moving-transform", init,
        "--transform", f"SyN{step}",
        "--metric", f"CC[{TEMPLATE_REF},{subject},1,2]",
        "--convergence", convergence,
        "--shrink-factors", shrink,
        "--smoothing-sigmas", smoothing,
    ]
