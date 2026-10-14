"""Remove the face (and, if asked, the eyes) from a scan and, if asked, put the template's
face and eyes in their place."""

from __future__ import annotations

import nibabel as nib
import numpy as np


def keep_mask(
    face_mask_in_subject: nib.Nifti1Image, eye_mask_in_subject: nib.Nifti1Image | None = None
) -> nib.Nifti1Image:
    """Turn the face mask (already on the scan's voxel grid) into the deface mask.

    The deface mask is 1 where the scan is kept and 0 over the face, and over the eyes too
    when their mask is given.
    """
    remove = np.asanyarray(face_mask_in_subject.dataobj) != 0
    if eye_mask_in_subject is not None:
        remove |= np.asanyarray(eye_mask_in_subject.dataobj) != 0
    return _like(face_mask_in_subject, (~remove).astype(np.float32))


def fill_region(
    face_mask_in_subject: nib.Nifti1Image,
    eye_mask_in_subject: nib.Nifti1Image | None,
    face: bool,
    eyes: bool,
) -> nib.Nifti1Image:
    """Return the region to fill with the template: 1 over the face (if `face`) and over
    the eyes (if `eyes`), 0 elsewhere. Both masks are already on the scan's voxel grid."""
    fill = np.zeros(face_mask_in_subject.shape[:3], bool)
    if face:
        fill |= np.asanyarray(face_mask_in_subject.dataobj) != 0
    if eyes and eye_mask_in_subject is not None:
        fill |= np.asanyarray(eye_mask_in_subject.dataobj) != 0
    return _like(face_mask_in_subject, fill.astype(np.float32))


def deface(subject: nib.Nifti1Image, keep: nib.Nifti1Image) -> nib.Nifti1Image:
    """Set the removed region (the face, and the eyes if they are in `keep`) to zero, leaving
    the rest of the scan as it was.

    The result keeps the scan's own data type (an int16 scan stays int16), so every voxel
    outside the face is stored exactly as before. A scan stored with a scale factor and offset
    is saved as float32, because zero may not be representable in its stored type. A 4D scan,
    such as several GRE echoes in one file, is masked one volume at a time.
    """
    data = np.asanyarray(subject.dataobj)  # in the stored type unless the file is rescaled
    mask = np.asanyarray(keep.dataobj) != 0
    mask = mask.reshape(mask.shape + (1,) * (data.ndim - mask.ndim))
    if data.dtype != subject.get_data_dtype():  # rescaled on disk: keep the old float32 output
        return _like(subject, np.where(mask, data, 0))
    header = subject.header.copy()
    header.set_slope_inter(None, None)  # values are stored as they are; no rescaling
    return nib.Nifti1Image(np.where(mask, data, 0).astype(data.dtype), subject.affine, header)


def reface(
    defaced: nib.Nifti1Image,
    keep: nib.Nifti1Image,
    template_ref: nib.Nifti1Image,
    template_brain: nib.Nifti1Image,
    fill: nib.Nifti1Image | None = None,
) -> tuple[nib.Nifti1Image, float]:
    """Fill the removed face, the removed eyes, or both with the template's.

    The template T1w and brain mask must already be warped onto the scan. The template
    is scaled so that the template's median brain intensity matches the scan's. `fill` is the
    region to fill (see `fill_region`); by default it is everything that was removed. Returns
    the refaced image and that scale factor.
    """
    subject = np.asanyarray(defaced.dataobj, dtype=np.float32)
    ref = np.asanyarray(template_ref.dataobj, dtype=np.float32)
    brain = np.asanyarray(template_brain.dataobj) > 0
    removed = np.asanyarray(keep.dataobj) == 0
    face = removed if fill is None else np.asanyarray(fill.dataobj) != 0
    scale = float(np.median(subject[brain & ~removed]) / np.median(ref[brain]))
    return _like(defaced, np.where(face, scale * ref, subject)), scale


def _like(image: nib.Nifti1Image, data: np.ndarray) -> nib.Nifti1Image:
    """Return `data` as a float32 NIfTI with the same header and affine as `image`."""
    header = image.header.copy()
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(data.astype(np.float32), image.affine, header)
