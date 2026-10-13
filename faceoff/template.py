"""The template files FaceOff registers to: a modified version of the MNI152 2020 template."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import nibabel as nib
import numpy as np

from .template_files import PREFIX, ZENODO_RECORD, fetch_missing, is_complete

# Template folder, first match wins:
#   1. FACEOFF_TEMPLATE_DIR, if set;
#   2. faceoff/data, when the files were bundled into the installed wheel (checked against the
#      published checksums);
#   3. a per-user cache folder; the files are downloaded there on first use.
_BUNDLED_DIR = Path(__file__).resolve().parent / "data"


def _template_dir() -> Path:
    if os.environ.get("FACEOFF_TEMPLATE_DIR"):
        return Path(os.environ["FACEOFF_TEMPLATE_DIR"])
    if is_complete(_BUNDLED_DIR):
        return _BUNDLED_DIR
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "faceoff" / f"zenodo-{ZENODO_RECORD}"


TEMPLATE_DIR = _template_dir()

TEMPLATE_REF = TEMPLATE_DIR / f"{PREFIX}T1w_ref.nii.gz"
# Brain mask limits the voxels considered by the affine and deface-SyN registration stages.
TEMPLATE_BRAIN_MASK = TEMPLATE_DIR / f"{PREFIX}brain_mask.nii.gz"
# Region the reface-SyN stage is fitted over.
TEMPLATE_REFACE_MASK = TEMPLATE_DIR / f"{PREFIX}reface_mask.nii.gz"
# Face (and ears) region to be removed: 1 = remove, 0 = keep.
TEMPLATE_FACE_MASK = TEMPLATE_DIR / f"{PREFIX}face_mask.nii.gz"
# Template z-slices (voxel indices, end exclusive) kept in the _tal output unless --no-crop.
TEMPLATE_CROP_Z = (70, 264)


def ensure_template(log: Callable[[str], None] = lambda message: None) -> None:
    """Download any missing or corrupt template file. Raises RuntimeError on failure."""
    fetch_missing(TEMPLATE_DIR, log=log)


def brain_centre_lps() -> np.ndarray:
    """Centroid of the template brain mask in LPS physical coordinates."""
    mask = nib.load(TEMPLATE_BRAIN_MASK)
    voxel = np.argwhere(np.asanyarray(mask.dataobj) > 0).mean(axis=0)
    ras = mask.affine @ np.append(voxel, 1.0)
    return (ras * np.array([-1.0, -1.0, 1.0, 1.0]))[:3]


def ref_origin_z() -> float:
    """World z of the template's first slice."""
    return float(nib.load(TEMPLATE_REF).affine[2, 3])
