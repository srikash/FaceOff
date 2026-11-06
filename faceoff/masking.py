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
    return _mask_like(face_mask_in_subject, ~remove)


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
    return _mask_like(face_mask_in_subject, fill)


def deface(subject: nib.Nifti1Image, keep: nib.Nifti1Image) -> nib.Nifti1Image:
    """Set the removed region (the face, and the eyes if they are in `keep`) to zero, leaving
    the rest of the scan as it was.

    The result keeps the scan's own data type (an int16 scan stays int16), so every voxel
    outside the face is stored exactly as before. A scan stored with a scale factor and offset
    is saved as float32, because zero may not be representable in its stored type. A 4D scan,
    such as several GRE echoes in one file, is masked across all volumes.
    """
    data = np.asanyarray(subject.dataobj)  # in the stored type unless the file is rescaled
    mask = np.asanyarray(keep.dataobj) != 0
    mask = mask.reshape(mask.shape + (1,) * (data.ndim - mask.ndim))
    if data.dtype != subject.get_data_dtype():  # rescaled on disk: keep the old float32 output
        return _like(subject, np.where(mask, data, 0))
    header = _scrubbed(subject.header)
    header.set_slope_inter(None, None)  # values are stored as they are; no rescaling
    return nib.Nifti1Image(np.where(mask, data, 0), subject.affine, header)


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
    subject = np.asanyarray(defaced.dataobj)  # in its own type; only copied where it is used
    ref = np.asanyarray(template_ref.dataobj, dtype=np.float32)
    if isinstance(template_ref.dataobj, np.ndarray) and np.shares_memory(ref, template_ref.dataobj):
        ref = ref.copy()  # ref is scaled in place below; never change the caller's array
    brain = np.asanyarray(template_brain.dataobj) > 0
    removed = np.asanyarray(keep.dataobj) == 0
    face = removed if fill is None else np.asanyarray(fill.dataobj) != 0
    subject_values = subject[brain & ~removed].astype(np.float32)
    reference_values = ref[brain]
    if not subject_values.size or not reference_values.size:
        raise ValueError("Cannot reface: the brain region is empty.")
    denominator = np.median(reference_values, overwrite_input=True)
    numerator = np.median(subject_values, overwrite_input=True)
    if not np.isfinite(numerator) or not np.isfinite(denominator):
        raise ValueError("Cannot reface: brain intensities are invalid.")
    if numerator <= 0 or denominator <= 0:
        raise ValueError(
            "Cannot reface: the median brain intensity is zero or negative, so the template "
            "cannot be scaled to this scan (MP2RAGE UNI images often have values around zero)."
        )
    scale = float(numerator / denominator)
    if not np.isfinite(scale):
        raise ValueError("Cannot reface: brain intensity scale is invalid.")
    extra_axes = (1,) * (subject.ndim - face.ndim)  # a (x, y, z, 1) scan, as in deface()
    face, ref = face.reshape(face.shape + extra_axes), ref.reshape(ref.shape + extra_axes)
    # Built in the template's buffer: the template scaled over the filled region, the scan
    # elsewhere. This saves two scan-sized float32 copies at 0.5 mm voxels.
    np.multiply(ref, scale, out=ref)
    np.copyto(ref, subject, where=~face)
    return _like(defaced, ref), scale


def _scrubbed(header: nib.Nifti1Header) -> nib.Nifti1Header:
    """Return a copy of the header without its free-text fields and extensions, which scanners
    and converters sometimes fill with names, dates or a whole DICOM header. This clears those
    fields only; it does not make a file anonymous (see docs/usage.md)."""
    header = nib.Nifti1Header.from_header(header)  # also turns a NIfTI-2 header into NIfTI-1
    for field in ("descrip", "aux_file", "db_name", "intent_name"):
        header[field] = b""
    header.extensions = nib.nifti1.Nifti1Extensions()
    return header


def _mask_like(image: nib.Nifti1Image, mask: np.ndarray) -> nib.Nifti1Image:
    """Return a 0/1 mask like `image`. In memory it is uint8 (a quarter of float32), and the
    header says float32, so the file written from it is the same as before."""
    header = _scrubbed(image.header)
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(mask.astype(np.uint8, copy=False), image.affine, header)


def _like(image: nib.Nifti1Image, data: np.ndarray) -> nib.Nifti1Image:
    """Return `data` as a float32 NIfTI with the same header and affine as `image`."""
    header = _scrubbed(image.header)
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(data.astype(np.float32, copy=False), image.affine, header)
