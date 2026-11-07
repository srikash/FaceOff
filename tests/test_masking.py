import gzip
import struct

import nibabel as nib
import numpy as np
import pytest

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
    fill = masking.fill_region(
        _img([[[1, 0, 0, 0]]]), _img([[[0, 1, 0, 0]]]), face=False, eyes=True
    )
    refaced, _ = masking.reface(subject, keep, template_ref, template_brain, fill)
    assert np.asanyarray(refaced.dataobj).ravel().tolist() == [0, 20, 10, 10]


def test_reface_rejects_empty_brain():
    import pytest

    image = _img([[[1, 1]]])
    empty = _img([[[0, 0]]])
    with pytest.raises(ValueError, match="brain region is empty"):
        masking.reface(image, image, image, empty)


def test_reface_rejects_invalid_brain_intensities():
    import pytest

    keep = _img([[[1]]])
    brain = _img([[[1]]])
    for subject, reference in [(float("nan"), 1), (1, float("inf"))]:
        with pytest.raises(ValueError, match="brain intensities are invalid"):
            masking.reface(_img([[[subject]]]), keep, _img([[[reference]]]), brain)


def test_reface_rejects_a_zero_or_negative_median_brain_intensity():
    import pytest

    keep = _img([[[1]]])
    brain = _img([[[1]]])
    for subject, reference in [(1, 0), (0, 1), (-0.3, 1), (1, -2)]:
        with pytest.raises(ValueError, match="zero or negative"):
            masking.reface(_img([[[subject]]]), keep, _img([[[reference]]]), brain)


def test_reface_handles_a_scan_with_a_length_one_fourth_axis():
    keep = np.ones((6, 6, 6), np.uint8)
    keep[:2] = 0  # the removed face
    ref = np.full((6, 6, 6), 50, np.float32)
    brain = np.ones((6, 6, 6), np.uint8)
    subject = np.full((6, 6, 6, 1), 10, np.float32)
    subject[:2] = 0
    refaced, scale = masking.reface(_img(subject), _img(keep), _img(ref), _img(brain), None)
    assert refaced.shape == (6, 6, 6, 1)
    assert scale == pytest.approx(0.2)
    np.testing.assert_allclose(np.asanyarray(refaced.dataobj), 10, rtol=1e-6)


def _dirty_scan(data):
    scan = nib.Nifti1Image(data, np.eye(4))
    scan.header["descrip"] = b"PATIENT NAME"
    scan.header["aux_file"] = b"visit-3"
    scan.header.extensions.append(nib.nifti1.Nifti1Extension(6, b"comment with a name"))
    return scan


def _assert_clean(path):
    reloaded = nib.load(path)
    assert reloaded.header["descrip"] == b"" and reloaded.header["aux_file"] == b""
    assert len(reloaded.header.extensions) == 0
    with gzip.open(path) as raw:  # vox_offset sits at byte 108; no extension means 352
        assert struct.unpack("<f", raw.read(112)[108:112])[0] == 352


def test_the_free_text_header_fields_and_extensions_are_cleared(tmp_path):
    data = np.arange(8, dtype=np.int16).reshape(2, 2, 2)
    keep = _img(np.ones((2, 2, 2)))
    defaced = masking.deface(_dirty_scan(data), keep)
    nib.save(defaced, tmp_path / "defaced.nii.gz")
    _assert_clean(tmp_path / "defaced.nii.gz")
    np.testing.assert_array_equal(
        np.asanyarray(nib.load(tmp_path / "defaced.nii.gz").dataobj), data
    )
    ref = _img(np.full((2, 2, 2), 5))
    refaced, _ = masking.reface(_dirty_scan(data.astype(np.float32) + 1), keep, ref, keep)
    nib.save(refaced, tmp_path / "refaced.nii.gz")
    _assert_clean(tmp_path / "refaced.nii.gz")


def test_reface_never_changes_the_callers_template_image():
    keep = np.ones((6, 6, 6), np.uint8)
    keep[:2] = 0
    reference = np.full((6, 6, 6), 50, np.float32)
    template_ref = _img(reference)
    masking.reface(
        _img(np.full((6, 6, 6), 10, np.float32)),
        _img(keep),
        template_ref,
        _img(np.ones((6, 6, 6), np.uint8)),
        None,
    )
    assert (np.asanyarray(template_ref.dataobj) == 50).all()
