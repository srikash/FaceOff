"""Register the scan to the template, then bring template images (such as the face mask) onto
the scan.

`register` runs the ANTs steps: a centre-of-mass start, rigid, affine, and the SyN steps if
asked for. The ANTs file names, the flags, and the order in which transforms are applied are
all kept in this file. The rest of FaceOff only calls `Transforms.to_subject`.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import NamedTuple

import nibabel as nib
import numpy as np

from .ants import AntsRunner
from .scratch import Workspace
from .template import Template


class Stage(Enum):
    """Which registration moves a template image onto the scan.

    AFFINE: the affine only. NONLINEAR_BRAIN: the affine, then the --syn warps (whole head
    with MI, then the brain with CC). NONLINEAR_FACE: those, then the warp fitted over the face
    (MI), so the template face and eyes match the scan's more closely.
    """

    AFFINE = "affine"
    NONLINEAR_BRAIN = "nonlinear brain"
    NONLINEAR_FACE = "nonlinear face"


class _SynSchedule(NamedTuple):
    """The settings for one SyN step. `metric` is filled in with the template and the scan."""

    metric: str
    step: str  # gradient step and regularisation
    convergence: str
    shrink: str
    smoothing: str


_MI = "MI[{fixed},{moving},1,32]"  # dense: every voxel, 32 bins
_CC = "CC[{fixed},{moving},1,2]"
# The face SyN stops at half resolution: the full-resolution level took ~75% of its time for
# a negligible gain in face fit. It uses dense MI: on the test scan it took 34 s against
# 4 min 35 s for CC, for a face fit (correlation) of 0.843 against 0.863.
_REFACE_SYN = _SynSchedule(_MI, "[0.2,3,0]", "[100x100x70x50,1e-6,10]", "10x6x4x2", "5x3x2x1vox")
# --syn: the same MI schedule as the face SyN over the whole head, then CC inside the brain.
_HEAD_SYN = _REFACE_SYN
_BRAIN_SYN = _SynSchedule(_CC, "[0.1,3,0]", "[50x25,1e-6,10]", "2x1", "1x0vox")

_AFFINE_PREFIX = "affine_"
_HEAD_PREFIX = "head_"
_BRAIN_PREFIX = "brain_"
_FACE_PREFIX = "face_"


class Transforms:
    """The registration of one scan to the template (the files sit in the run's temporary
    folder): the affine, then any nonlinear warps, each with its inverse."""

    def __init__(
        self,
        ants: AntsRunner,
        ws: Workspace,
        subject: Path,
        brain_warps: list[Path],
        face_warp: Path | None,
    ) -> None:
        self._ants = ants
        self._ws = ws
        self._subject = subject
        self._brain_warps = brain_warps  # inverse warps of --syn, in the order they were fitted
        self._face_warp = face_warp  # inverse warp of the face registration, if it was run

    @property
    def affine(self) -> Path:
        """Return the registration's affine file; the reorientation is taken from it.

        It moves the scan into template space. As a mapping of coordinates, it takes template
        points to scan points (the ITK convention used throughout this file).
        """
        return self._ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")

    @property
    def affine_lps(self) -> np.ndarray:
        """Return the affine as a 4x4 matrix in LPS world coordinates (mm), mapping template
        points to scan points: the ITK convention, as in the affine file."""
        matrix = self._ws.path("affine_matrix.txt")
        if not matrix.exists():
            self._ants.run("ConvertTransformFile", ["3", self.affine, matrix, "--hm"])
        return np.loadtxt(matrix)

    def to_subject(
        self,
        template_image: Path,
        output: Path,
        stage: Stage,
        interpolation: str = "GenericLabel",
        reference: Path | None = None,
    ) -> None:
        """Move a template image, such as the face mask, onto the scan using this registration.

        The whole chain of transforms goes to one antsApplyTransforms call, so the image is
        resampled once. The result is on the scan's voxel grid, or on the grid of `reference`
        if given: any other image in the same scanner space, 3D or 4D (for a 4D image, its 3D
        grid is used). Use "GenericLabel" interpolation for masks and "Linear" for intensity
        images.
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
        # Order matters: the inverse affine first, then the inverse warps in the order they
        # were fitted, the last-fitted warp last. The reverse order silently gives wrong output.
        warps: list[Path] = []
        if stage is not Stage.AFFINE:
            warps += self._brain_warps
        if stage is Stage.NONLINEAR_BRAIN and not self._brain_warps:
            raise ValueError("No nonlinear brain registration (--syn) was run.")
        if stage is Stage.NONLINEAR_FACE:
            if self._face_warp is None:
                raise ValueError("No nonlinear face registration was run.")
            warps.append(self._face_warp)
        chain = ["--transform", f"[{self.affine},1]"]
        for warp in warps:
            chain += ["--transform", str(warp)]
        return chain


def register(
    ants: AntsRunner,
    ws: Workspace,
    subject: Path,
    template: Template,
    *,
    syn: bool,
    face: bool,
) -> Transforms:
    """Register the scan to the template: centre-of-mass start, rigid, affine, then the
    nonlinear brain registration if `syn`, and the nonlinear face registration if `face`.
    Returns the result, ready to move template images onto the scan.
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

    # Each SyN step is its own call, starting from the affine and the warps fitted before it,
    # and writes its own warp and inverse warp. They are not merged into one file: the steps
    # end at different resolutions (2 mm and 1 mm warps), which ANTs cannot combine. They are
    # still applied together, in one antsApplyTransforms call (see Transforms.to_subject).
    # The nonlinear brain registration (--syn) is not required (the affine alone already gives
    # the deface mask) and is kept for completeness: it fits the whole head with MI, then the
    # brain with CC. The nonlinear face registration starts from that (or the affine) and is
    # fitted over the reface mask.
    affine = ws.path(f"{_AFFINE_PREFIX}0GenericAffine.mat")
    forward: list[Path] = []  # warps fitted so far, scan to template, in fitting order
    inverse: list[Path] = []

    def fit(prefix: str, mask: Path | None, schedule: _SynSchedule) -> Path:
        """Run one SyN step and return its inverse warp. ANTs numbers a step's warp after the
        transforms it starts from (affine = 0)."""
        start = [*reversed(forward), affine]  # ANTs order: the last-applied transform first
        args = _syn_args(subject, template, start, mask, ws.path(prefix), schedule)
        ants.run("antsRegistration", args)
        number = len(start)
        forward.append(ws.path(f"{prefix}{number}Warp.nii.gz"))
        inverse.append(ws.path(f"{prefix}{number}InverseWarp.nii.gz"))
        return inverse[-1]

    if syn:
        fit(_HEAD_PREFIX, None, _HEAD_SYN)
        fit(_BRAIN_PREFIX, template.brain_mask, _BRAIN_SYN)
    brain_warps = list(inverse)
    face_warp = fit(_FACE_PREFIX, template.reface_mask, _REFACE_SYN) if face else None
    return Transforms(ants, ws, subject, brain_warps, face_warp)


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
    start: list[Path],
    mask: Path | None,
    prefix: Path,
    schedule: _SynSchedule,
) -> list[str | Path]:
    """Return the antsRegistration settings for one SyN step, masked by `mask` (or over the
    whole image if None) and starting from the transforms in `start` (ANTs order: the
    last-applied transform first)."""
    initial: list[str | Path] = []
    for transform in start:
        initial += ["--initial-moving-transform", transform]
    return [
        "--verbose", "0",
        "--random-seed", "13",
        "--dimensionality", "3",
        "--float", "1",
        # Write only this step's warp. With collapsing on, ANTs also rewrites the starting
        # transforms, and fails when a starting warp is on a coarser grid (the 2 mm head warp).
        "--collapse-output-transforms", "0",
        "--output", prefix,  # transforms only: no warped images
        "--use-histogram-matching", "0",
        "--winsorize-image-intensities", "[0.005,0.995]",
        *(["--masks", f"[{mask},1]"] if mask else []),
        *initial,
        "--transform", f"SyN{schedule.step}",
        "--metric", schedule.metric.format(fixed=template.t1w, moving=subject),
        "--convergence", schedule.convergence,
        "--shrink-factors", schedule.shrink,
        "--smoothing-sigmas", schedule.smoothing,
    ]
