import nibabel as nib
import numpy as np

from faceoff import masking


def _img(data):
    return nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4))


def test_keep_mask_inverts_face_mask():
    face = _img([[[1, 0], [0, 1]]])
    keep = masking.keep_mask(face)
    assert np.asanyarray(keep.dataobj).ravel().tolist() == [0, 1, 1, 0]


def test_deface_zeroes_face_and_keeps_the_data_type(tmp_path):
    subject = nib.Nifti1Image(np.array([[[5, 6], [7, 8]]], dtype=np.int16), np.eye(4))
    keep = _img([[[0, 1], [1, 0]]])
    defaced = masking.deface(subject, keep)
    assert np.asanyarray(defaced.dataobj).ravel().tolist() == [0, 6, 7, 0]
    assert defaced.get_data_dtype() == np.int16
    nib.save(defaced, tmp_path / "d.nii.gz")
    saved = nib.load(tmp_path / "d.nii.gz")
    assert saved.get_data_dtype() == np.int16
    assert np.asanyarray(saved.dataobj).ravel().tolist() == [0, 6, 7, 0]


def test_deface_of_a_rescaled_file_is_float32(tmp_path):
    stored = nib.Nifti1Image(np.array([[[5, 6], [7, 8]]], dtype=np.int16), np.eye(4))
    stored.header.set_slope_inter(2.0, 10.0)  # on disk: value = 2 * stored + 10
    nib.save(stored, tmp_path / "s.nii.gz")
    defaced = masking.deface(nib.load(tmp_path / "s.nii.gz"), _img([[[0, 1], [1, 0]]]))
    assert defaced.get_data_dtype() == np.float32
    assert np.asanyarray(defaced.dataobj).ravel().tolist() == [0, 22, 24, 0]


def test_reface_fills_face_with_scaled_template():
    subject = _img([[[0, 10, 10, 10]]])  # voxel 0 is the removed face
    keep = _img([[[0, 1, 1, 1]]])
    template_ref = _img([[[40, 20, 20, 20]]])
    template_brain = _img([[[0, 1, 1, 1]]])
    refaced, scale = masking.reface(subject, keep, template_ref, template_brain)
    assert scale == 0.5
    assert np.asanyarray(refaced.dataobj).ravel().tolist() == [20, 10, 10, 10]


def test_keep_mask_removes_the_eyes_too():
    keep = masking.keep_mask(_img([[[1, 0, 0, 0]]]), _img([[[0, 1, 0, 0]]]))
    assert np.asanyarray(keep.dataobj).ravel().tolist() == [0, 0, 1, 1]


def test_reface_fill_limits_what_is_put_back():
    subject = _img([[[0, 0, 10, 10]]])  # voxels 0 (face) and 1 (eye) were removed
    keep = _img([[[0, 0, 1, 1]]])
    template_ref = _img([[[40, 40, 20, 20]]])
    template_brain = _img([[[0, 0, 1, 1]]])
    fill = masking.fill_region(_img([[[1, 0, 0, 0]]]), _img([[[0, 1, 0, 0]]]), face=False, eyes=True)
    refaced, _ = masking.reface(subject, keep, template_ref, template_brain, fill)
    assert np.asanyarray(refaced.dataobj).ravel().tolist() == [0, 20, 10, 10]
