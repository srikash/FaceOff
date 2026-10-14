"""deface.run end to end, with a fake ANTs that writes plausible outputs and a synthetic
template."""

import re

import nibabel as nib
import numpy as np
import pytest

from faceoff import deface
from faceoff.reorient import Crop


class FakeAnts:
    """Writes the files FaceOff reads back after each ANTs call. Registration does nothing,
    the affine is the identity, and each template image comes out differently on the
    reference grid, so a test can tell them apart:

    - face mask: 1 where x < 2;
    - template T1w: 50 over the face (x < 2) and 20 elsewhere;
    - brain mask: 1 where x >= 2;
    - eye mask: 1 where x == 2.
    """

    def __init__(self) -> None:
        self.references: list[str] = []

    def run(self, tool, args):
        args = [str(a) for a in args]
        if tool == "antsApplyTransforms":
            reference = args[args.index("--reference-image") + 1]
            moving = args[args.index("--input") + 1]
            self.references.append(reference)
            grid = nib.load(reference)
            face = np.zeros(grid.shape[:3], np.float32)
            face[:2] = 1
            if "eye_mask" in moving:
                data = np.zeros(grid.shape[:3], np.float32)
                data[2] = 1
            elif "T1w_ref" in moving:
                data = np.where(face > 0, 50, 20)
            elif "brain_mask" in moving:
                data = 1 - face
            else:
                data = face
            nib.save(nib.Nifti1Image(data.astype(np.float32), grid.affine), args[args.index("--output") + 1])
        elif tool == "ConvertTransformFile":
            np.savetxt(args[2], np.eye(4))


def _save(path, data, affine=None):
    nib.save(nib.Nifti1Image(data, np.eye(4) if affine is None else affine), path)
    return path


def test_extra_images_and_tal_mask(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    other_grid = _save(  # same space, half the resolution
        tmp_path / "inv1.nii.gz", np.full((3, 5, 4), 5, np.int16), np.diag([2.0, 1, 1, 1])
    )
    echoes = _save(tmp_path / "gre.nii.gz", np.full((6, 5, 4, 3), 9, np.int16))
    options = deface.Options(
        threads=1, crop=False, extra_images=(other_grid, echoes), template=template
    )
    ants = FakeAnts()

    outputs = deface.run(subject, options, ants=ants)

    assert all(path.exists() for path in outputs.written())
    mask = np.asanyarray(nib.load(outputs.deface_mask).dataobj)
    tal_mask = nib.load(outputs.tal_deface_mask)
    assert np.array_equal(np.asanyarray(tal_mask.dataobj), mask)
    assert tal_mask.header["sform_code"] == 4

    inv1, gre = (np.asanyarray(nib.load(p).dataobj) for p in outputs.extra_defaced)
    assert inv1.shape == (3, 5, 4) and (inv1[:2] == 0).all() and (inv1[2:] == 5).all()
    assert gre.shape == (6, 5, 4, 3) and (gre[:2] == 0).all() and (gre[2:] == 9).all()
    assert [p.name for p in outputs.extra_tal_defaced] == ["inv1_tal_defaced.nii.gz",
                                                           "gre_tal_defaced.nii.gz"]
    # The 4D image is warped onto through a 3D stand-in for its grid.
    assert ants.references[1] == str(other_grid)
    assert ants.references[2].endswith("grid_for_face_mask_in_extra1.nii.gz")


def test_enucleate_removes_the_eyes_too(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    plain = deface.run(subject, deface.Options(threads=1, crop=False, template=template), ants=FakeAnts())
    assert (np.asanyarray(nib.load(plain.defaced).dataobj)[2] == 7).all()
    options = deface.Options(threads=1, crop=False, enucleate=True, template=template)
    outputs = deface.run(subject, options, ants=FakeAnts())
    defaced = np.asanyarray(nib.load(outputs.defaced).dataobj)
    assert (defaced[:3] == 0).all() and (defaced[3:] == 7).all()
    assert outputs.refaced is None


def test_renucleate_puts_back_only_the_eyes(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, renucleate=True, template=template)
    outputs = deface.run(subject, options, ants=FakeAnts())
    refaced = np.asanyarray(nib.load(outputs.refaced).dataobj)
    np.testing.assert_allclose(refaced[:2], 0)  # the face stays removed
    np.testing.assert_allclose(refaced[2], 7)  # template eyes: 20 * (7 / 20)
    np.testing.assert_allclose(refaced[3:], 7)
    assert (np.asanyarray(nib.load(outputs.defaced).dataobj)[:3] == 0).all()


def test_reface_with_renucleate_puts_back_face_and_eyes(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, reface=True, renucleate=True, template=template)
    refaced = np.asanyarray(nib.load(deface.run(subject, options, ants=FakeAnts()).refaced).dataobj)
    np.testing.assert_allclose(refaced[:2], 17.5)  # template face
    np.testing.assert_allclose(refaced[2:], 7)


def _titles(path):
    html = path.read_text()
    return re.findall(r"<span>(.*?)</span>", html), html.count("<img")


def test_qc_page_is_written_by_default_with_the_defaced_scan_only(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, template=template)
    outputs = deface.run(subject, options, ants=FakeAnts())
    assert outputs.qc == tmp_path / "t1_faceoff_qc.html" and outputs.qc in outputs.written()
    assert _titles(outputs.qc) == (["defaced"], 1)


def test_qc_page_adds_refaced_with_reface_or_renucleate_and_a_gif_per_extra(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 5, np.int16))
    for flags in ({"reface": True}, {"renucleate": True}):
        options = deface.Options(
            threads=1, crop=False, qc=True, extra_images=(extra,), template=template, **flags
        )
        outputs = deface.run(subject, options, ants=FakeAnts())
        assert _titles(outputs.qc) == (["defaced", "refaced", "defaced"], 2)


def test_no_qc_page_with_no_qc(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    outputs = deface.run(subject, options, ants=FakeAnts())
    assert outputs.qc is None and not list(tmp_path.glob("*_faceoff_qc.html"))


def test_reface_fills_the_face_with_the_scaled_template(tmp_path, template):
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, reface=True, crop=False, template=template)

    outputs = deface.run(subject, options, ants=FakeAnts())

    refaced = np.asanyarray(nib.load(outputs.refaced).dataobj)
    # Brain scale: subject 7 / template 20 = 0.35, so the template face (50) becomes 17.5.
    np.testing.assert_allclose(refaced[:2], 17.5)
    np.testing.assert_allclose(refaced[2:], 7)
    assert outputs.tal_refaced.exists()


def test_input_is_not_an_extra_image(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.zeros((2, 2, 2), np.int16))
    options = deface.Options(threads=1, extra_images=(subject,), template=template)
    with pytest.raises(ValueError, match="input itself"):
        deface.run(subject, options, ants=FakeAnts())


class RecordingReporter(deface.Reporter):
    """Notes down the crops a run reports."""

    def __init__(self) -> None:
        self.crops: list[Crop] = []

    def cropped(self, crop: Crop) -> None:
        self.crops.append(crop)


def test_crop_is_reported_once_and_applied_to_the_tal_outputs(tmp_path, template):
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 400), 7, np.int16))
    reporter = RecordingReporter()

    outputs = deface.run(subject, deface.Options(threads=1, template=template), reporter, FakeAnts())

    assert reporter.crops == [Crop(axis=2, first=120, last=314, size=400)]
    for path in (outputs.tal_defaced, outputs.tal_deface_mask):
        assert nib.load(path).shape == (6, 5, 194)


def test_no_reorient_writes_transforms_but_no_tal_files(tmp_path, template):
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 300), 7, np.int16))
    reporter = RecordingReporter()
    options = deface.Options(threads=1, reorient=False, template=template)

    outputs = deface.run(subject, options, reporter, FakeAnts())

    assert outputs.txn_itk.exists() and outputs.txn_fsl.exists()
    assert not list(tmp_path.glob("*_tal_*"))
    assert reporter.crops == []


def test_missing_extra_image_is_an_error(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.zeros((2, 2, 2), np.int16))
    options = deface.Options(threads=1, extra_images=(tmp_path / "nope.nii.gz",), template=template)
    with pytest.raises(FileNotFoundError, match="Extra image not found"):
        deface.run(subject, options, ants=FakeAnts())
