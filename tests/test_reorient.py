from pathlib import Path

import nibabel as nib
import numpy as np

from conftest import write_template
from faceoff.reorient import TalReorientation, _itk_to_flirt
from faceoff.template import TEMPLATE_CROP_Z, Template

NOWHERE = Template(Path("/nowhere"))  # for tests that never read template files


def _rotation(axis: int, deg: float) -> np.ndarray:
    a = np.radians(deg)
    m = np.eye(4)
    i, j = [(1, 2), (0, 2), (0, 1)][axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = np.cos(a), -np.sin(a), np.sin(a), np.cos(a)
    return m


def test_rigid_part_of_a_rotation_is_itself():
    centre = np.array([10.0, -5.0, 3.0])
    rotation = _rotation(2, 20)
    rotation[:3, 3] = centre - rotation[:3, :3] @ centre  # rotation about `centre`
    tal = TalReorientation.from_affine_matrix(rotation, NOWHERE, centre)
    np.testing.assert_allclose(tal.rigid_lps, rotation, atol=1e-12)


def test_scaling_is_removed_and_centre_is_preserved():
    centre = np.array([1.0, 2.0, 3.0])
    affine = _rotation(2, 15) @ np.diag([1.1, 0.9, 1.0, 1.0])
    affine[:3, 3] = [4.0, 5.0, 6.0]
    tal = TalReorientation.from_affine_matrix(affine, NOWHERE, centre)
    rotation = tal.rigid_lps[:3, :3]
    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(tal.rigid_lps @ [*centre, 1], affine @ [*centre, 1], atol=1e-12)


def test_identity_flirt_for_identical_grids():
    img = nib.Nifti1Image(np.zeros((4, 5, 6)), np.diag([-1.0, 1.0, 1.0, 1.0]))
    np.testing.assert_allclose(_itk_to_flirt(np.eye(4), img, img), np.eye(4), atol=1e-12)


def test_fsl_matrix_matches_c3d_on_a_rotated_non_1mm_grid(tmp_path):
    """Expected values come from c3d_affine_tool -ras2fsl on the same images and .tfm."""
    ref_affine = np.diag([2.0, 2.0, 2.0, 1.0])
    ref_affine[:3, 3] = [-10, -12, -14]
    template = write_template(tmp_path / "template", ref_affine, shape=(40, 44, 48))
    src_affine = _rotation(0, 25) @ np.diag([1.2, 1.0, 1.5, 1.0])
    src_affine[:3, 3] = [5, -3, 8]
    source = tmp_path / "src.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((30, 32, 34), np.int16), src_affine), source)
    rigid = _rotation(2, 20)
    rigid[:3, 3] = [3, -2, 4]

    TalReorientation(rigid, template).write_transforms(source, tmp_path / "x.tfm", tmp_path / "x.mat")

    c3d = [[0.939693, -0.309976, 0.144544, 29.4913],
           [0.34202, 0.851651, -0.397131, -7.33693],
           [0.0, 0.422618, 0.906308, 18.0],
           [0.0, 0.0, 0.0, 1.0]]
    np.testing.assert_allclose(np.loadtxt(tmp_path / "x.mat"), c3d, atol=1e-4)


def test_header_only_reorientation_keeps_data_and_codes(tmp_path):
    data = np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6)
    source = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), source)
    tal = TalReorientation(_rotation(2, 10), NOWHERE)
    [crop] = tal.write_images([(source, tmp_path / "out.nii.gz")], crop=False)
    out = nib.load(tmp_path / "out.nii.gz")
    assert crop is None
    assert np.array_equal(np.asanyarray(out.dataobj), data)
    assert out.get_data_dtype() == np.int16
    assert out.header["sform_code"] == 4 and out.header["qform_code"] == 4


def test_crop_range_follows_the_template_slice_thickness(tmp_path):
    """Slice indices are converted through the template's affine, so a 2 mm template gives a
    range twice as long (the old code assumed 1 mm slices)."""
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    affine[:3, 3] = [0, 0, -100]
    template = write_template(tmp_path / "t2mm", affine)
    low, high = template.crop_z_mm
    assert (low, high) == (-100 + 2 * (TEMPLATE_CROP_Z[0] - 0.5), -100 + 2 * (TEMPLATE_CROP_Z[1] - 0.5))


def test_crop_on_an_oblique_scan_keeps_only_slices_inside_the_template_range(tmp_path):
    template = write_template(tmp_path / "template")  # 1 mm, origin 0: keeps z 69.5 to 263.5
    low, high = template.crop_z_mm
    affine = _rotation(0, 30) @ np.diag([1.0, 1.0, 1.2, 1.0])  # tilted 30 degrees, 1.2 mm slices
    shape = (10, 12, 300)
    data = np.arange(np.prod(shape), dtype=np.int32).reshape(shape)
    source, target = tmp_path / "oblique.nii.gz", tmp_path / "tal.nii.gz"
    nib.save(nib.Nifti1Image(data, affine), source)

    [crop] = TalReorientation(np.eye(4), template).write_images([(source, target)], crop=True)

    assert crop.axis == 2
    centre_z = [
        nib.affines.apply_affine(affine, [(shape[0] - 1) / 2, (shape[1] - 1) / 2, k])[2]
        for k in range(shape[2])
    ]
    kept = [k for k, z in enumerate(centre_z) if low <= z < high]
    assert (crop.first, crop.last) == (kept[0], kept[-1] + 1)
    out = nib.load(target)
    assert np.array_equal(np.asanyarray(out.dataobj), data[:, :, crop.first:crop.last])
    # Voxel (i, j, 0) of the cropped image is where voxel (i, j, first) was.
    np.testing.assert_allclose(
        out.affine @ [3, 4, 0, 1], affine @ [3, 4, crop.first, 1], atol=1e-9
    )


def test_images_on_the_same_grid_get_the_same_crop(tmp_path):
    template = write_template(tmp_path / "template")
    affine = np.eye(4)
    pairs = []
    for name in ("a", "b"):
        path = tmp_path / f"{name}.nii.gz"
        nib.save(nib.Nifti1Image(np.zeros((4, 4, 300), np.int16), affine), path)
        pairs.append((path, tmp_path / f"{name}_tal.nii.gz"))
    first, second = TalReorientation(np.eye(4), template).write_images(pairs, crop=True)
    assert first == second and (first.first, first.last) == (70, 264)
