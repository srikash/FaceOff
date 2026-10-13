"""Remove the face from a subject image and, optionally, insert the template face."""

from __future__ import annotations

import nibabel as nib
import numpy as np


def keep_mask(face_mask_in_subject: nib.Nifti1Image) -> nib.Nifti1Image:
    """Invert the warped face mask: 1 where data is kept, 0 over the face."""
    keep = (np.asanyarray(face_mask_in_subject.dataobj) == 0).astype(np.float32)
    return _like(face_mask_in_subject, keep)


def deface(subject: nib.Nifti1Image, keep: nib.Nifti1Image) -> nib.Nifti1Image:
    """Zero the subject over the face (float32 output). A 4D subject (for example several
    echoes) is masked volume by volume."""
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
    """Fill the removed region with the template face (both template images already in
    subject space), scaled so its median brain intensity matches the subject's.

    Returns the refaced image and the intensity scale.
    """
    subject = np.asanyarray(defaced.dataobj, dtype=np.float32)
    ref = np.asanyarray(template_ref.dataobj, dtype=np.float32)
    brain = np.asanyarray(template_brain.dataobj) > 0
    face = np.asanyarray(keep.dataobj) == 0
    scale = float(np.median(subject[brain & ~face]) / np.median(ref[brain]))
    return _like(defaced, np.where(face, scale * ref, subject)), scale


def _like(image: nib.Nifti1Image, data: np.ndarray) -> nib.Nifti1Image:
    header = image.header.copy()
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(data.astype(np.float32), image.affine, header)
