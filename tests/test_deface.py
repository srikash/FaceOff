"""deface.run end to end, with a fake ANTs that writes plausible outputs and a synthetic
template."""

import re

import nibabel as nib
import numpy as np
import pytest

from conftest import StandInRegistration, write_template
from faceoff import deface
from faceoff.inputs import ScanToDeface
from faceoff.registration import Stage
from faceoff.reorient import Crop


@pytest.fixture
def template(tmp_path):
    """The synthetic template with simple patterns along x (1 mm voxels), so a test can tell
    the moved template images apart on the scan:

    - face mask: 1 where x < 2;
    - template T1w: 50 over the face (x < 2) and 20 elsewhere;
    - brain mask: 1 where x >= 2;
    - eye mask: 1 where x == 2.
    """
    template = write_template(tmp_path / "template")
    x = np.indices((8, 8, 8))[0]
    for path, data in [
        (template.face_mask, (x < 2).astype(np.uint8)),
        (template.t1w, np.where(x < 2, 50, 20).astype(np.int16)),
        (template.brain_mask, (x >= 2).astype(np.uint8)),
        (template.eye_mask, (x == 2).astype(np.uint8)),
    ]:
        nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return template


def _save(path, data, affine=None):
    nib.save(nib.Nifti1Image(data, np.eye(4) if affine is None else affine), path)
    return path


def test_extra_images_and_tal_mask(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    other_grid = _save(  # same space, half the resolution
        tmp_path / "inv1.nii.gz", np.full((3, 5, 4), 5, np.int16), np.diag([2.0, 1, 1, 1])
    )
    echoes = _save(tmp_path / "gre.nii.gz", np.full((6, 5, 4, 3), 9, np.int16))
    options = deface.Options(threads=1, crop=False, template=template)
    scan = ScanToDeface(subject, (other_grid, echoes))
    outputs = deface.run(scan, options, registration=StandInRegistration())

    assert all(path.exists() for path in outputs.written())
    mask = np.asanyarray(nib.load(outputs.deface_mask).dataobj)
    tal_mask = nib.load(outputs.tal_deface_mask)
    assert np.array_equal(np.asanyarray(tal_mask.dataobj), mask)
    assert tal_mask.header["sform_code"] == 4

    inv1, gre = (np.asanyarray(nib.load(p).dataobj) for p in outputs.extra_defaced)
    # inv1 has 2 mm voxels along x: only its first slice (x = 0 mm) is inside the face.
    assert inv1.shape == (3, 5, 4) and (inv1[:1] == 0).all() and (inv1[1:] == 5).all()
    assert gre.shape == (6, 5, 4, 3) and (gre[:2] == 0).all() and (gre[2:] == 9).all()
    assert [p.name for p in outputs.extra_tal_defaced] == ["inv1_tal_defaced.nii.gz",
                                                           "gre_tal_defaced.nii.gz"]


def test_the_face_is_removed_where_the_registration_puts_it(tmp_path, template):
    """The scan sits 1 mm further along x than the template, so the face (template slices
    0 and 1) lands on the scan's slices 1 and 2; slice 0 is outside the template."""
    shifted = np.eye(4)
    shifted[0, 3] = 1.0
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration(shifted))
    defaced = np.asanyarray(nib.load(outputs.defaced).dataobj)
    assert (defaced[1:3] == 0).all() and (defaced[0] == 7).all() and (defaced[3:] == 7).all()


def test_enucleate_removes_the_eyes_too(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    plain = deface.run(ScanToDeface(subject), deface.Options(threads=1, crop=False, template=template), registration=StandInRegistration())
    assert (np.asanyarray(nib.load(plain.defaced).dataobj)[2] == 7).all()
    options = deface.Options(threads=1, crop=False, enucleate=True, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    defaced = np.asanyarray(nib.load(outputs.defaced).dataobj)
    assert (defaced[:3] == 0).all() and (defaced[3:] == 7).all()
    assert outputs.refaced is None


def test_renucleate_puts_back_only_the_eyes(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, renucleate=True, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    refaced = np.asanyarray(nib.load(outputs.refaced).dataobj)
    np.testing.assert_allclose(refaced[:2], 0)  # the face stays removed
    np.testing.assert_allclose(refaced[2], 7)  # template eyes: 20 * (7 / 20)
    np.testing.assert_allclose(refaced[3:], 7)
    assert (np.asanyarray(nib.load(outputs.defaced).dataobj)[:3] == 0).all()


def test_reface_with_renucleate_puts_back_face_and_eyes(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, reface=True, renucleate=True, template=template)
    refaced = np.asanyarray(nib.load(deface.run(ScanToDeface(subject), options, registration=StandInRegistration()).refaced).dataobj)
    np.testing.assert_allclose(refaced[:2], 17.5)  # template face
    np.testing.assert_allclose(refaced[2:], 7)


def _titles(path):
    html = path.read_text()
    return re.findall(r"<span>(.*?)</span>", html), html.count("<img")


def test_qc_page_is_written_by_default_with_the_defaced_scan_only(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    assert outputs.qc == tmp_path / "t1_faceoff_qc.html" and outputs.qc in outputs.written()
    assert _titles(outputs.qc) == (["defaced"], 1)


def test_qc_page_adds_refaced_with_reface_or_renucleate_and_a_gif_per_extra(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 5, np.int16))
    for flags in ({"reface": True}, {"renucleate": True}):
        options = deface.Options(threads=1, crop=False, qc=True, template=template, **flags)
        outputs = deface.run(ScanToDeface(subject, (extra,)), options,
                             registration=StandInRegistration())
        assert _titles(outputs.qc) == (["defaced", "refaced", "defaced"], 2)


def test_no_qc_page_with_no_qc(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    assert outputs.qc is None and not list(tmp_path.glob("*_faceoff_qc.html"))


def test_reface_fills_the_face_with_the_scaled_template(tmp_path, template):
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, reface=True, crop=False, template=template)

    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())

    refaced = np.asanyarray(nib.load(outputs.refaced).dataobj)
    # Brain scale: subject 7 / template 20 = 0.35, so the template face (50) becomes 17.5.
    np.testing.assert_allclose(refaced[:2], 17.5)
    np.testing.assert_allclose(refaced[2:], 7)
    assert outputs.tal_refaced.exists()


class RecordingReporter(deface.Reporter):
    """Notes down the crops and warnings a run reports."""

    def __init__(self) -> None:
        self.crops: list[Crop] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def cropped(self, crop: Crop) -> None:
        self.crops.append(crop)


@pytest.mark.parametrize(("syn", "face_stage"), [
    (False, Stage.AFFINE), (True, Stage.NONLINEAR_BRAIN),
])
def test_the_eyes_always_use_the_face_registration(tmp_path, template, syn, face_stage):
    """The face mask goes with the affine (or --syn's brain registration); the eye mask, for
    the scan and for each extra image, with the nonlinear face registration."""
    subject = _save(tmp_path / "t.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 5, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, enucleate=True, syn=syn,
                             template=template)
    registration = StandInRegistration()
    deface.run(ScanToDeface(subject, (extra,)), options, registration=registration)
    stages = {(name.split("desc-")[1], stage) for name, stage in registration.moved}
    assert stages == {("face_mask.nii.gz", face_stage), ("eye_mask.nii.gz", Stage.NONLINEAR_FACE)}
    assert len(registration.moved) == 4  # both masks, for the scan and the extra image


def test_the_eye_hole_and_the_template_eyes_come_from_the_same_registration(tmp_path, template):
    """Give the face registration a 1 mm shift that the affine does not have: the eyes are
    removed where that registration puts them (slice 3), and filled from it, while the face
    stays where the affine puts it (slices 0 and 1)."""
    shift = np.eye(4)
    shift[0, 3] = 1.0
    registration = StandInRegistration(per_stage={Stage.NONLINEAR_FACE: shift})
    subject = _save(tmp_path / "t.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, renucleate=True, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=registration)
    defaced = np.asanyarray(nib.load(outputs.defaced).dataobj)
    refaced = np.asanyarray(nib.load(outputs.refaced).dataobj)
    assert (defaced[:2] == 0).all() and (defaced[2] == 7).all() and (defaced[3] == 0).all()
    np.testing.assert_allclose(refaced[3], 7)  # template eye (20) scaled to the scan (7 / 20)
    np.testing.assert_allclose(refaced[:2], 0)  # the face stays removed


def test_reface_with_enucleate_puts_the_eyes_back_like_renucleate(tmp_path, template):
    results = []
    for name, flags in (("a", {"reface": True, "enucleate": True}),
                        ("b", {"reface": True, "renucleate": True}),
                        ("c", {"reface": True, "enucleate": True, "renucleate": True})):
        scan = _save(tmp_path / f"{name}.nii.gz", np.full((6, 5, 4), 7, np.int16))
        options = deface.Options(threads=1, crop=False, qc=False, template=template, **flags)
        outputs = deface.run(ScanToDeface(scan), options, registration=StandInRegistration())
        results.append((np.asanyarray(nib.load(outputs.defaced).dataobj),
                        np.asanyarray(nib.load(outputs.refaced).dataobj)))
    defaced, refaced = results[0]
    assert (defaced[:3] == 0).all()  # the face and the eyes are removed ...
    np.testing.assert_allclose(refaced[:2], 17.5)  # ... the template face goes back ...
    np.testing.assert_allclose(refaced[2], 7)  # ... and so do the template eyes
    for other_defaced, other_refaced in results[1:]:  # --renucleate is then redundant
        np.testing.assert_array_equal(defaced, other_defaced)
        np.testing.assert_array_equal(refaced, other_refaced)


def test_reface_alone_leaves_the_eyes_as_they_are(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, reface=True, template=template)
    outputs = deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    assert (np.asanyarray(nib.load(outputs.defaced).dataobj)[2] == 7).all()


def test_a_failing_qc_page_does_not_stop_the_defacing(tmp_path, template, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("no pixels today")

    monkeypatch.setattr(deface.qc, "write_page", broken)
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    reporter = RecordingReporter()
    options = deface.Options(threads=1, crop=False, template=template)
    outputs = deface.run(ScanToDeface(subject), options, reporter, StandInRegistration())
    assert outputs.qc is None
    assert outputs.txn_itk.exists() and outputs.txn_fsl.exists() and outputs.tal_defaced.exists()
    assert not list(tmp_path.glob("*_faceoff_qc.html"))
    assert any("no pixels today" in message for message in reporter.warnings)


def test_crop_is_reported_once_and_applied_to_the_tal_outputs(tmp_path, template):
    origin = np.eye(4)
    origin[2, 3] = -150  # slices at z -150 to 249 mm; the crop range -100 to 125 keeps 50 to 274
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 400), 7, np.int16), origin)
    reporter = RecordingReporter()

    outputs = deface.run(ScanToDeface(subject), deface.Options(threads=1, template=template), reporter, StandInRegistration())

    assert reporter.crops == [Crop(axis=2, first=50, last=275, size=400)]
    for path in (outputs.tal_defaced, outputs.tal_deface_mask):
        assert nib.load(path).shape == (6, 5, 225)


def test_no_reorient_writes_transforms_but_no_tal_files(tmp_path, template):
    subject = _save(tmp_path / "t1w.nii.gz", np.full((6, 5, 300), 7, np.int16))
    reporter = RecordingReporter()
    options = deface.Options(threads=1, reorient=False, template=template)

    outputs = deface.run(ScanToDeface(subject), options, reporter, StandInRegistration())

    assert outputs.txn_itk.exists() and outputs.txn_fsl.exists()
    assert not list(tmp_path.glob("*_tal_*"))
    assert reporter.crops == []
