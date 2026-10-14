"""Remove the face from a scan and, if asked, put the template's face in its place."""

from __future__ import annotations

import nibabel as nib
import numpy as np


def keep_mask(face_mask_in_subject: nib.Nifti1Image) -> nib.Nifti1Image:
    """Turn the face mask (already on the scan's voxel grid) into the deface mask.

    The deface mask is 1 where the scan is kept and 0 over the face and ears.
    """
    keep = (np.asanyarray(face_mask_in_subject.dataobj) == 0).astype(np.float32)
    return _like(face_mask_in_subject, keep)


def deface(subject: nib.Nifti1Image, keep: nib.Nifti1Image) -> nib.Nifti1Image:
    """Set the face and ears to zero, leaving the rest of the scan as it was.

    The result is saved as float32. A 4D scan, such as several GRE echoes in one file, is
    masked one volume at a time.
    """
    data = np.asanyarray(subject.dataobj).astype(np.float32)
    mask = np.asanyarray(keep.dataobj)
    data *= mask.reshape(mask.shape + (1,) * (data.ndim - mask.ndim))
    return _like(subject, data)


def reface(
    defaced: nib.Nifti1Image,
    keep: nib.Nifti1Image,
    template_ref: nib.Nifti1Image,
    template_brain: nib.Nifti1Image,
) -> tuple[nib.Nifti1Image, float]:
    """Fill the removed face with the template's face.

    The template T1w and brain mask must already be warped onto the scan. The template face
    is scaled so that the template's median brain intensity matches the scan's. Returns the
    refaced image and that scale factor.
    """
    subject = np.asanyarray(defaced.dataobj, dtype=np.float32)
    ref = np.asanyarray(template_ref.dataobj, dtype=np.float32)
    brain = np.asanyarray(template_brain.dataobj) > 0
    face = np.asanyarray(keep.dataobj) == 0
    scale = float(np.median(subject[brain & ~face]) / np.median(ref[brain]))
    return _like(defaced, np.where(face, scale * ref, subject)), scale


def _like(image: nib.Nifti1Image, data: np.ndarray) -> nib.Nifti1Image:
    """Return `data` as a float32 NIfTI with the same header and affine as `image`."""
    header = image.header.copy()
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(data.astype(np.float32), image.affine, header)
