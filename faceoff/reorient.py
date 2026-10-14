"""Put scans in template ("tal") orientation by changing only their headers, and save the
rotation as ITK and FSL transform files.

Background: ANTs and ITK transforms work in LPS world coordinates and map template points to
scan points; NIfTI headers map voxels to RAS world coordinates. The helpers below convert
between the two.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

from .ants import AntsRunner
from .scratch import Workspace
from .template import Template

_LPS_FLIP = np.diag([-1.0, -1.0, 1.0, 1.0])


@dataclass(frozen=True)
class Crop:
    """Which of the scan's own slices were kept: `first` up to (not including) `last`, along
    voxel `axis`, out of `size` slices."""

    axis: int
    first: int
    last: int  # exclusive
    size: int


class TalReorientation:
    """The rotation between a scan and the template, taken from the registration's affine.

    Scaling and shearing are left out, so applying it never changes the brain's shape.
    """

    def __init__(self, rigid_lps: np.ndarray, template: Template) -> None:
        self.rigid_lps = rigid_lps
        self.template = template

    @classmethod
    def from_affine_matrix(
        cls, affine_lps: np.ndarray, template: Template, centre_lps: np.ndarray | None = None
    ) -> TalReorientation:
        """Take the rotation part of a 4x4 affine (LPS, template to scan).

        The rotation turns about `centre_lps`, by default the centre of the template brain,
        so the brain ends up in the same place as with the full affine.
        """
        centre = template.brain_centre_lps if centre_lps is None else centre_lps
        left, _, right = np.linalg.svd(affine_lps[:3, :3])
        rotation = left @ right
        rigid = np.eye(4)
        rigid[:3, :3] = rotation
        rigid[:3, 3] = affine_lps[:3, :3] @ centre + affine_lps[:3, 3] - rotation @ centre
        return cls(rigid, template)

    @classmethod
    def from_ants_affine(
        cls, ants: AntsRunner, ws: Workspace, affine_mat: Path, template: Template
    ) -> TalReorientation:
        """Read the registration's affine file (via ANTs ConvertTransformFile) and take its
        rotation part."""
        matrix_file = ws.path("affine_matrix.txt")
        ants.run("ConvertTransformFile", ["3", affine_mat, matrix_file, "--hm"])
        return cls.from_affine_matrix(np.loadtxt(matrix_file), template)

    def write_transforms(self, source: Path, itk_out: Path, fsl_out: Path) -> None:
        """Save the rotation as an ITK transform (.tfm) and an FSL FLIRT matrix (.mat).

        Both take `source` to the template grid.
        """
        params = " ".join(
            f"{v:.12g}" for v in [*self.rigid_lps[:3, :3].ravel(), *self.rigid_lps[:3, 3]]
        )
        itk_out.write_text(
            "#Insight Transform File V1.0\n#Transform 0\n"
            "Transform: AffineTransform_double_3_3\n"
            f"Parameters: {params}\nFixedParameters: 0 0 0\n"
        )
        flirt = _itk_to_flirt(self.rigid_lps, nib.load(source), nib.load(self.template.t1w))
        fsl_out.write_text("".join(" ".join(f"{v:.10f}" for v in row) + "\n" for row in flirt))

    def write_images(
        self, sources_and_targets: Sequence[tuple[Path, Path]], crop: bool
    ) -> list[Crop | None]:
        """Write each source image in template orientation to its target, without resampling.

        Only the header changes: the voxel values and data type stay exactly as they were,
        and the rotation goes into the affine. With `crop`, whole slices are dropped along
        the voxel axis that points closest to the template's head-foot direction; the slices
        kept are those whose centres fall inside template slices TEMPLATE_CROP_Z. Images on
        the same voxel grid get the same crop. Returns, for each image, what was cropped (or
        None).
        """
        crops: dict[tuple, Crop] = {}
        results: list[Crop | None] = []
        for source, target in sources_and_targets:
            image = nib.load(source)
            affine = _LPS_FLIP @ np.linalg.inv(self.rigid_lps) @ _LPS_FLIP @ image.affine
            data = np.asanyarray(image.dataobj)
            cropped = None
            if crop:
                grid = (image.shape[:3], affine.round(6).tobytes())
                if grid not in crops:
                    crops[grid] = _crop_slices(image.shape[:3], affine, self.template.crop_z_mm)
                cropped = crops[grid]
                data = np.take(data, np.arange(cropped.first, cropped.last), axis=cropped.axis)
                affine[:3, 3] += affine[:3, cropped.axis] * cropped.first
            tal = nib.Nifti1Image(data, affine, image.header)
            tal.set_sform(affine, code=4)  # 4 = MNI152 space
            tal.set_qform(affine, code=4)
            nib.save(tal, target)
            results.append(cropped)
        return results


def _crop_slices(
    shape: tuple[int, ...], affine: np.ndarray, z_range_mm: tuple[float, float]
) -> Crop:
    """Work out which slices of a scan (already in template orientation) have their centres
    inside the world z range `z_range_mm`."""
    z_min, z_max = z_range_mm
    axis = int(np.argmax(np.abs(affine[2, :3])))
    centres = np.tile((np.array(shape) - 1) / 2, (shape[axis], 1))
    centres[:, axis] = np.arange(shape[axis])
    z = nib.affines.apply_affine(affine, centres)[:, 2]
    keep = np.flatnonzero((z >= z_min) & (z < z_max))
    if keep.size == 0:
        raise ValueError("Crop would remove every slice.")
    return Crop(axis, int(keep[0]), int(keep[-1]) + 1, shape[axis])


def _fsl_voxel_matrix(img: nib.Nifti1Image) -> np.ndarray:
    """Return FSL's voxel-to-mm matrix for an image (FSL flips x when the affine's
    determinant is positive)."""
    zooms = img.header.get_zooms()[:3]
    fsl = np.diag([*zooms, 1.0])
    if np.linalg.det(img.affine[:3, :3]) > 0:
        fsl[0, 0] = -zooms[0]
        fsl[0, 3] = (img.shape[0] - 1) * zooms[0]
    return fsl


def _itk_to_flirt(itk_lps: np.ndarray, src: nib.Nifti1Image, ref: nib.Nifti1Image) -> np.ndarray:
    """Convert an ITK transform (template to scan) into a FLIRT matrix (scan to template)."""
    ref_vox_to_src_vox = np.linalg.inv(src.affine) @ (_LPS_FLIP @ itk_lps @ _LPS_FLIP) @ ref.affine
    return (
        _fsl_voxel_matrix(ref)
        @ np.linalg.inv(ref_vox_to_src_vox)
        @ np.linalg.inv(_fsl_voxel_matrix(src))
    )
