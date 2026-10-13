"""Reorientation to template ("tal") space, header only, with transforms saved as ITK and FSL.

ITK/ANTs transforms act on LPS physical coordinates and map template points to subject
points; NIfTI affines map voxels to RAS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

from .ants import AntsRunner
from .template import TEMPLATE_CROP_Z, TEMPLATE_REF, brain_centre_lps, ref_origin_z
from .workspace import Workspace

_LPS_FLIP = np.diag([-1.0, -1.0, 1.0, 1.0])


@dataclass(frozen=True)
class Crop:
    """Slices kept along one voxel axis."""

    axis: int
    first: int
    last: int  # exclusive
    size: int


class TalReorientation:
    """The rotation component of the registration affine (LPS, template -> subject)."""

    def __init__(self, rigid_lps: np.ndarray) -> None:
        self.rigid_lps = rigid_lps

    @classmethod
    def from_affine_matrix(
        cls, affine_lps: np.ndarray, centre_lps: np.ndarray | None = None
    ) -> TalReorientation:
        """Polar decomposition of a 4x4 affine, fixing `centre_lps` (default: template brain
        centroid) as the full affine does."""
        centre = brain_centre_lps() if centre_lps is None else centre_lps
        u, _, vt = np.linalg.svd(affine_lps[:3, :3])
        rotation = u @ vt
        rigid = np.eye(4)
        rigid[:3, :3] = rotation
        rigid[:3, 3] = affine_lps[:3, :3] @ centre + affine_lps[:3, 3] - rotation @ centre
        return cls(rigid)

    @classmethod
    def from_ants_affine(
        cls, ants: AntsRunner, ws: Workspace, affine_mat: Path
    ) -> TalReorientation:
        """From the registration's ITK affine file (read with ConvertTransformFile)."""
        matrix_file = ws.path("affine_matrix.txt")
        ants.run("ConvertTransformFile", ["3", affine_mat, matrix_file, "--hm"])
        return cls.from_affine_matrix(np.loadtxt(matrix_file))

    def write_transforms(self, source: Path, itk_out: Path, fsl_out: Path) -> None:
        """Save as ITK text transform and FLIRT matrix; both map `source` to the template grid."""
        params = " ".join(
            f"{v:.12g}" for v in [*self.rigid_lps[:3, :3].ravel(), *self.rigid_lps[:3, 3]]
        )
        itk_out.write_text(
            "#Insight Transform File V1.0\n#Transform 0\n"
            "Transform: AffineTransform_double_3_3\n"
            f"Parameters: {params}\nFixedParameters: 0 0 0\n"
        )
        flirt = _itk_to_flirt(self.rigid_lps, nib.load(source), nib.load(TEMPLATE_REF))
        fsl_out.write_text("".join(" ".join(f"{v:.10f}" for v in row) + "\n" for row in flirt))

    def write_image(self, source: Path, output: Path, crop: bool) -> Crop | None:
        """Write `source` in template orientation without resampling.

        Only the header changes: voxel data and data type are kept and the rotation is absorbed
        into the affine. With `crop`, whole slices are dropped along the voxel axis closest to
        the template's superior direction, keeping the planes whose centres lie in the world-z
        range of template slices TEMPLATE_CROP_Z. Returns what was cropped, if anything.
        """
        img = nib.load(source)
        affine = _LPS_FLIP @ np.linalg.inv(self.rigid_lps) @ _LPS_FLIP @ img.affine
        data = np.asanyarray(img.dataobj)

        cropped = None
        if crop:
            cropped = _crop_slices(img.shape, affine)
            data = np.take(data, np.arange(cropped.first, cropped.last), axis=cropped.axis)
            affine[:3, 3] += affine[:3, cropped.axis] * cropped.first

        tal = nib.Nifti1Image(data, affine, img.header)
        tal.set_sform(affine, code=4)  # 4 = MNI152 space
        tal.set_qform(affine, code=4)
        nib.save(tal, output)
        return cropped


def _crop_slices(shape: tuple[int, ...], affine: np.ndarray) -> Crop:
    shape = shape[:3]  # a 4D image is cropped the same way in every volume
    z0 = ref_origin_z()
    z_min = z0 + TEMPLATE_CROP_Z[0] - 0.5
    z_max = z0 + TEMPLATE_CROP_Z[1] - 0.5
    axis = int(np.argmax(np.abs(affine[2, :3])))
    centres = np.tile((np.array(shape) - 1) / 2, (shape[axis], 1))
    centres[:, axis] = np.arange(shape[axis])
    z = nib.affines.apply_affine(affine, centres)[:, 2]
    keep = np.flatnonzero((z >= z_min) & (z < z_max))
    if keep.size == 0:
        raise ValueError("Crop would remove every slice.")
    return Crop(axis, int(keep[0]), int(keep[-1]) + 1, shape[axis])


def _fsl_voxel_matrix(img: nib.Nifti1Image) -> np.ndarray:
    """Voxel -> FSL scaled-mm matrix (x is flipped for radiological-positive-det images)."""
    zooms = img.header.get_zooms()[:3]
    fsl = np.diag([*zooms, 1.0])
    if np.linalg.det(img.affine[:3, :3]) > 0:
        fsl[0, 0] = -zooms[0]
        fsl[0, 3] = (img.shape[0] - 1) * zooms[0]
    return fsl


def _itk_to_flirt(itk_lps: np.ndarray, src: nib.Nifti1Image, ref: nib.Nifti1Image) -> np.ndarray:
    """FLIRT matrix (src FSL-mm -> ref FSL-mm) for an ITK transform mapping ref -> src."""
    ref_vox_to_src_vox = np.linalg.inv(src.affine) @ (_LPS_FLIP @ itk_lps @ _LPS_FLIP) @ ref.affine
    return (
        _fsl_voxel_matrix(ref)
        @ np.linalg.inv(ref_vox_to_src_vox)
        @ np.linalg.inv(_fsl_voxel_matrix(src))
    )
