"""Read a NIfTI file with the type the rest of FaceOff expects."""

from __future__ import annotations

import os

import nibabel as nib


def load_image(path: str | os.PathLike[str]) -> nib.Nifti1Image:
    """Load a NIfTI file. NIfTI-2 files are accepted too (their class is a subclass)."""
    image = nib.load(path)
    if not isinstance(image, nib.Nifti1Image):
        raise ValueError(f"{path} is not a NIfTI image.")  # noqa: TRY004 (callers catch ValueError)
    return image
