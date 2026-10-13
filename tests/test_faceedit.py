import nibabel as nib
import numpy as np

from faceoff import faceedit


def _img(data):
    return nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4))


def test_keep_mask_inverts_face_mask():
    face = _img([[[1, 0], [0, 1]]])
    keep = faceedit.keep_mask(face)
    assert np.asanyarray(keep.dataobj).ravel().tolist() == [0, 1, 1, 0]


def test_deface_zeroes_face_and_returns_float32():
    subject = nib.Nifti1Image(np.array([[[5, 6], [7, 8]]], dtype=np.int16), np.eye(4))
    keep = _img([[[0, 1], [1, 0]]])
    defaced = faceedit.deface(subject, keep)
    assert np.asanyarray(defaced.dataobj).ravel().tolist() == [0, 6, 7, 0]
    assert defaced.get_data_dtype() == np.float32


def test_reface_fills_face_with_scaled_template():
    subject = _img([[[0, 10, 10, 10]]])  # voxel 0 is the removed face
    keep = _img([[[0, 1, 1, 1]]])
    template_ref = _img([[[40, 20, 20, 20]]])
    template_brain = _img([[[0, 1, 1, 1]]])
    refaced, scale = faceedit.reface(subject, keep, template_ref, template_brain)
    assert scale == 0.5
    assert np.asanyarray(refaced.dataobj).ravel().tolist() == [20, 10, 10, 10]
