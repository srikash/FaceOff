"""load_image: NIfTI-1 and NIfTI-2 files load; other image types are refused."""

import nibabel as nib
import numpy as np
import pytest

from faceoff.images import load_image


@pytest.mark.parametrize("kind", [nib.Nifti1Image, nib.Nifti2Image])
def test_nifti1_and_nifti2_files_load(tmp_path, kind):
    path = tmp_path / "scan.nii.gz"
    nib.save(kind(np.ones((3, 4, 5), np.int16), np.eye(4)), path)
    assert load_image(path).shape == (3, 4, 5)


def test_a_non_nifti_image_is_refused(tmp_path):
    path = tmp_path / "scan.img"
    nib.save(nib.Nifti1Pair(np.ones((3, 4, 5), np.int16), np.eye(4)), path)
    with pytest.raises(ValueError, match="not a NIfTI image"):
        load_image(path)
