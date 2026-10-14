"""Register the scan to the template, then bring template images (such as the face mask) onto
the scan.

`register` runs the ANTs steps: a centre-of-mass start, rigid, affine, and the SyN steps if
asked for. The ANTs file names, the flags, and the order in which transforms are applied are
all kept in this file. The rest of FaceOff only calls `Transforms.to_subject`.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import nibabel as nib
import numpy as np

from .ants import AntsRunner
from .scratch import Workspace
from .template import Template


class Stage(Enum):
    """Which registration to use when bringing a template image onto the scan.

    DEFACE: the affine (or, with --syn, the brain-masked SyN warp). REFACE: also the SyN warp
    fitted over the face, so the template face matches the scan's face more closely.
    """

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
    """The registration of one scan to the template (the files sit in the run's temporary
    folder)."""

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
        """Return the registration's affine file; the reorientation is taken from it.

        It moves the scan into template space. As a mapping of coordinates, it takes template
        points to scan points (the ITK convention used throughout this file).
        """
        return self._ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")

    def to_subject(
        self,
        template_image: Path,
        output: Path,
        stage: Stage,
        interpolation: str = "GenericLabel",
        reference: Path | None = None,
    ) -> None:
        """Move a template image, such as the face mask, onto the scan using this registration.

        The result is on the scan's voxel grid, or on the grid of `reference` if given: any
        other image in the same scanner space, 3D or 4D (for a 4D image, its 3D grid is
        used). Use "GenericLabel" interpolation for masks and "Linear" for intensity images.
        """
        grid = self._subject if reference is None else self._grid_of(reference, output)
        self._ants.run("antsApplyTransforms", [
            "--dimensionality", "3",
            "--interpolation", interpolation,
            "--reference-image", grid,
            "--input", template_image,
            "--output", output,
            "--verbose", "0",
            *self._inverse_chain(stage),
        ])

    def _grid_of(self, image: Path, output: Path) -> Path:
        """Return `image` itself if it is 3D; for a 4D image (such as several GRE echoes),
        write an empty 3D image on the same grid, because ANTs needs a 3D reference here."""
        loaded = nib.load(image)
        if loaded.ndim <= 3:
            return image
        grid = self._ws.path(f"grid_for_{output.name}")
        nib.save(nib.Nifti1Image(np.zeros(loaded.shape[:3], np.uint8), loaded.affine), grid)
        return grid

    def _inverse_chain(self, stage: Stage) -> list[str]:
        """Return the ANTs `--transform` arguments that take template space to the scan."""
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
    ants: AntsRunner,
    ws: Workspace,
    subject: Path,
    template: Template,
    *,
    syn: bool,
    reface: bool,
) -> Transforms:
    """Register the scan to the template: centre-of-mass start, rigid, affine, then SyN if
    `syn` or `reface` is set. Returns the result, ready to move template images onto the scan.
    """
    init = ws.path("init.mat")
    ants.run("antsAI", [
        "--dimensionality", "3",
        "--random-seed", "13",
        "--transform", "AlignCentersOfMass",
        "--masks", template.brain_mask,
        "--metric", f"MI[{template.t1w},{subject},32,Regular,0.25]",
        "--output", init,
    ])
    ants.run("antsRegistration", _affine_args(subject, init, ws.path(_AFFINE_PREFIX), template))
    affine = ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")

    # SyN stages are separate calls. The deface SyN (--syn) is not required (the affine alone
    # already gives the deface mask) and is kept for completeness; it starts from the affine
    # and is guided by the brain mask; the reface SyN starts from that warp (or the affine) and is
    # fitted over the reface mask.
    if syn:
        ants.run("antsRegistration", _syn_args(
            subject, template, affine, template.brain_mask, ws.path(_SYN_PREFIX), _DEFACE_SYN,
            write_composite=True,
        ))
    if reface:
        start = ws.path(f"{_SYN_PREFIX}Composite.h5") if syn else affine
        ants.run("antsRegistration", _syn_args(
            subject, template, start, template.reface_mask, ws.path(_FACE_PREFIX), _REFACE_SYN,
        ))
    return Transforms(ants, ws, subject, syn, reface)


def _affine_args(
    subject: Path, init: Path, prefix: Path, template: Template
) -> list[str | Path]:
    """Return the antsRegistration settings for the rigid and affine steps (brain-masked)."""
    brain_mask = f"[{template.brain_mask},1]"
    mi = f"MI[{template.t1w},{subject},1,32,Regular,0.25]"
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
    template: Template,
    init: Path,
    mask: Path,
    prefix: Path,
    schedule: tuple[str, str, str, str],
    write_composite: bool = False,
) -> list[str | Path]:
    """Return the antsRegistration settings for one SyN step, masked by `mask` and starting
    from `init` (the affine, or an earlier SyN result)."""
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
        "--metric", f"CC[{template.t1w},{subject},1,2]",
        "--convergence", convergence,
        "--shrink-factors", shrink,
        "--smoothing-sigmas", smoothing,
    ]
