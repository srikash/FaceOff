import nibabel as nib
import numpy as np

from faceoff.reorient import TalReorientation, _itk_to_flirt


def _rotation_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    m = np.eye(4)
    m[:2, :2] = [[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]
    return m


def test_rigid_part_of_a_rotation_is_itself():
    centre = np.array([10.0, -5.0, 3.0])
    rotation = _rotation_z(20)
    rotation[:3, 3] = centre - rotation[:3, :3] @ centre  # rotation about `centre`
    tal = TalReorientation.from_affine_matrix(rotation, centre)
    np.testing.assert_allclose(tal.rigid_lps, rotation, atol=1e-12)


def test_scaling_is_removed_and_centre_is_preserved():
    centre = np.array([1.0, 2.0, 3.0])
    affine = _rotation_z(15) @ np.diag([1.1, 0.9, 1.0, 1.0])
    affine[:3, 3] = [4.0, 5.0, 6.0]
    tal = TalReorientation.from_affine_matrix(affine, centre)
    rotation = tal.rigid_lps[:3, :3]
    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(tal.rigid_lps @ [*centre, 1], affine @ [*centre, 1], atol=1e-12)


def test_identity_flirt_for_identical_grids():
    img = nib.Nifti1Image(np.zeros((4, 5, 6)), np.diag([-1.0, 1.0, 1.0, 1.0]))
    np.testing.assert_allclose(_itk_to_flirt(np.eye(4), img, img), np.eye(4), atol=1e-12)


def test_header_only_reorientation_keeps_data_and_codes(tmp_path, monkeypatch):
    data = np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6)
    img = nib.Nifti1Image(data, np.diag([1.0, 1.0, 1.0, 1.0]))
    source = tmp_path / "in.nii.gz"
    nib.save(img, source)
    tal = TalReorientation(_rotation_z(10))
    crop = tal.write_image(source, tmp_path / "out.nii.gz", crop=False)
    out = nib.load(tmp_path / "out.nii.gz")
    assert crop is None
    assert np.array_equal(np.asanyarray(out.dataobj), data)
    assert out.get_data_dtype() == np.int16
    assert out.header["sform_code"] == 4 and out.header["qform_code"] == 4
