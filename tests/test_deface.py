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
    assert [p.name for p in outputs.extra_tal_defaced] == [
        "inv1_tal_defaced.nii.gz",
        "gre_tal_defaced.nii.gz",
    ]


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
    plain = deface.run(
        ScanToDeface(subject),
        deface.Options(threads=1, crop=False, template=template),
        registration=StandInRegistration(),
    )
    assert (np.asanyarray(nib.load(plain.defaced).dataobj)[2] == 7).all()
    options = deface.Options(
        threads=1, crop=False, enucleate=True, template=template, overwrite=True
    )
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
    refaced = np.asanyarray(
        nib.load(
            deface.run(ScanToDeface(subject), options, registration=StandInRegistration()).refaced
        ).dataobj
    )
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
        options = deface.Options(
            threads=1, crop=False, qc=True, template=template, overwrite=True, **flags
        )
        outputs = deface.run(
            ScanToDeface(subject, (extra,)), options, registration=StandInRegistration()
        )
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


@pytest.mark.parametrize(
    ("syn", "face_stage"),
    [
        (False, Stage.AFFINE),
        (True, Stage.NONLINEAR_BRAIN),
    ],
)
def test_the_eyes_always_use_the_face_registration(tmp_path, template, syn, face_stage):
    """The face mask goes with the affine (or --syn's brain registration); the eye mask, for
    the scan and for each extra image, with the nonlinear face registration."""
    subject = _save(tmp_path / "t.nii.gz", np.full((6, 5, 4), 7, np.int16))
    shifted = np.eye(4)
    shifted[0, 3] = 1  # another grid, so the extra image gets masks of its own
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 5, np.int16), shifted)
    options = deface.Options(
        threads=1, crop=False, qc=False, enucleate=True, syn=syn, template=template
    )
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
    for name, flags in (
        ("a", {"reface": True, "enucleate": True}),
        ("b", {"reface": True, "renucleate": True}),
        ("c", {"reface": True, "enucleate": True, "renucleate": True}),
    ):
        scan = _save(tmp_path / f"{name}.nii.gz", np.full((6, 5, 4), 7, np.int16))
        options = deface.Options(threads=1, crop=False, qc=False, template=template, **flags)
        outputs = deface.run(ScanToDeface(scan), options, registration=StandInRegistration())
        results.append(
            (
                np.asanyarray(nib.load(outputs.defaced).dataobj),
                np.asanyarray(nib.load(outputs.refaced).dataobj),
            )
        )
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

    outputs = deface.run(
        ScanToDeface(subject),
        deface.Options(threads=1, template=template),
        reporter,
        StandInRegistration(),
    )

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


def test_empty_primary_mask_stops_before_writing(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.ones((6, 5, 4), np.int16))
    nib.save(nib.Nifti1Image(np.zeros((8, 8, 8), np.uint8), np.eye(4)), template.face_mask)
    with pytest.raises(ValueError, match="face mask is empty"):
        deface.run(
            ScanToDeface(subject),
            deface.Options(threads=1, template=template),
            registration=StandInRegistration(),
        )
    assert not (tmp_path / "t1_defaced.nii.gz").exists()


def test_failed_qc_does_not_report_old_page(tmp_path, template, monkeypatch, capsys):
    from faceoff.messages import ConsoleReporter

    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    old_qc = tmp_path / "t1_faceoff_qc.html"
    old_qc.write_text("old page")

    def broken(*args, **kwargs):
        raise RuntimeError("no pixels today")

    monkeypatch.setattr(deface.qc, "write_page", broken)
    options = deface.Options(threads=1, crop=False, template=template, overwrite=True)
    outputs = deface.run(ScanToDeface(subject), options, ConsoleReporter(), StandInRegistration())
    assert outputs.qc is None
    assert not old_qc.exists()  # a page left over from the last run would show the wrong scan
    assert str(old_qc) not in capsys.readouterr().out


def test_failed_qc_that_cannot_clear_the_old_page_still_finishes(tmp_path, template, capsys):
    from faceoff.messages import ConsoleReporter

    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    blocked = tmp_path / "t1_faceoff_qc.html"
    blocked.mkdir()  # neither written over nor deleted as a file
    options = deface.Options(threads=1, crop=False, template=template, overwrite=True)
    outputs = deface.run(ScanToDeface(subject), options, ConsoleReporter(), StandInRegistration())
    assert outputs.qc is None and outputs.defaced.exists()
    text = capsys.readouterr().out
    assert "could not be removed" in text
    ticked = [line for line in text.splitlines() if line.strip().startswith("✓")]
    assert not any(line.endswith("t1_faceoff_qc.html") for line in ticked)
    assert any(line.endswith("t1_defaced.nii.gz") for line in ticked)  # the check can see ticks


def test_overwrite_replaces_existing_output(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    output = tmp_path / "t1_defaced.nii.gz"
    output.write_bytes(b"previous output")
    options = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    data = np.asanyarray(nib.load(output).dataobj)
    assert (data[:2] == 0).all() and (data[2:] == 7).all()


def test_a_mirroring_registration_stops_the_run_before_anything_is_written(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    mirror = np.diag([-1.0, 1.0, 1.0, 1.0])
    options = deface.Options(threads=1, crop=False, template=template)
    with pytest.raises(ValueError, match="mirrors the scan"):
        deface.run(ScanToDeface(subject), options, registration=StandInRegistration(mirror))
    assert sorted(path.name for path in tmp_path.iterdir() if path.is_file()) == ["t1.nii.gz"]


def test_reface_refuses_a_4d_scan_before_writing_anything(tmp_path, template):
    subject = _save(tmp_path / "gre.nii.gz", np.full((6, 5, 4, 3), 7, np.int16))
    options = deface.Options(threads=1, reface=True, template=template)
    with pytest.raises(ValueError, match="is 4D"):
        deface.check_inputs([ScanToDeface(subject)], options)
    with pytest.raises(ValueError, match="is 4D"):
        deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    assert [path.name for path in tmp_path.glob("gre_*")] == []
    deface.check_inputs([ScanToDeface(subject)], deface.Options(threads=1, template=template))


def test_an_extra_image_the_face_mask_misses_is_refused_and_nothing_is_written(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    far = np.eye(4)
    far[0, 3] = 500  # the extra's grid is far from the template's face
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 3, np.int16), far)
    options = deface.Options(threads=1, crop=False, template=template)
    with pytest.raises(ValueError, match=r"empty on inv1\.nii\.gz"):
        deface.run(ScanToDeface(subject, (extra,)), options, registration=StandInRegistration())
    assert sorted(path.name for path in tmp_path.iterdir() if path.is_file()) == [
        "inv1.nii.gz",
        "t1.nii.gz",
    ]


def test_a_crop_that_would_remove_every_slice_is_found_before_anything_is_written(
    tmp_path, template
):
    high = np.eye(4)
    high[2, 3] = 1000  # all slices lie above the crop range
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16), high)
    options = deface.Options(threads=1, template=template)
    with pytest.raises(ValueError, match="remove every slice"):
        deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    assert [path.name for path in tmp_path.glob("t1_*")] == []


def test_files_from_an_earlier_run_that_this_run_does_not_write_are_warned_about(
    tmp_path, template
):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, reface=True, template=template)
    deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    reporter = RecordingReporter()
    plain = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    deface.run(ScanToDeface(subject), plain, reporter, StandInRegistration())
    [warning] = [w for w in reporter.warnings if "earlier one" in w]
    assert "t1_refaced.nii.gz" in warning and "t1_faceoff_qc.html" in warning
    assert "t1_defaced.nii.gz" not in warning
    assert (tmp_path / "t1_refaced.nii.gz").exists()  # warned about, never deleted


def test_a_first_run_has_nothing_left_over_to_warn_about(tmp_path, template):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    reporter = RecordingReporter()
    options = deface.Options(threads=1, crop=False, template=template)
    deface.run(ScanToDeface(subject), options, reporter, StandInRegistration())
    assert not any("earlier one" in w for w in reporter.warnings)


def test_an_unusual_registration_scale_gives_a_warning_and_a_normal_one_does_not(
    tmp_path, template
):
    subject = _save(tmp_path / "t1.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    for scale, expect_warning in [(1.0, False), (1.1, False), (2.0, True), (0.5, True)]:
        reporter = RecordingReporter()
        stand_in = StandInRegistration(np.diag([scale, scale, scale, 1.0]))
        try:
            deface.run(ScanToDeface(subject), options, reporter, stand_in)
        except ValueError:  # the scaled stand-in may miss the face; only the warning matters
            pass
        assert any("stretches the template" in w for w in reporter.warnings) == expect_warning


def test_a_nifti2_input_is_defaced_and_written_as_nifti1_without_noise(tmp_path, template, capsys):
    path = tmp_path / "t1.nii.gz"
    nib.save(nib.Nifti2Image(np.full((6, 5, 4), 7, np.int16), np.eye(4)), path)
    capsys.readouterr()  # the test image's own saving may print; FaceOff must not
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    outputs = deface.run(ScanToDeface(path), options, registration=StandInRegistration())
    assert capsys.readouterr().err == ""
    original = nib.load(path)
    for written, code in [(outputs.defaced, None), (outputs.tal_defaced, 4)]:
        image = nib.load(written)
        assert type(image) is nib.Nifti1Image
        assert image.header.get_data_dtype() == np.int16
        want = code or int(original.header["sform_code"])
        assert int(image.header["sform_code"]) == want


def test_extra_images_on_the_inputs_grid_share_its_mask_and_others_get_their_own(
    tmp_path, template
):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    same = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 3, np.int16))
    shifted = np.eye(4)
    shifted[0, 3] = 1  # same size, other position: needs its own mask
    other = _save(tmp_path / "inv2.nii.gz", np.full((6, 5, 4), 3, np.int16), shifted)
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    registration = StandInRegistration()
    outputs = deface.run(ScanToDeface(subject, (same, other)), options, registration=registration)
    face_moves = [name for name, _ in registration.moved if "face_mask" in name]
    assert len(face_moves) == 2  # the input's grid once (shared with inv1), inv2 once
    np.testing.assert_array_equal(
        np.asanyarray(nib.load(outputs.extra_defaced[0]).dataobj)[:, :, :] == 0,
        np.asanyarray(nib.load(outputs.defaced).dataobj) == 0,
    )


def test_an_extra_image_damaged_past_its_header_stops_the_run_before_any_output(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extra = _save(tmp_path / "inv1.nii", np.arange(120, dtype=np.int16).reshape(6, 5, 4))
    extra.write_bytes(extra.read_bytes()[:-40])  # header intact, data cut short
    options = deface.Options(threads=1, crop=False, template=template)
    with pytest.raises(OSError, match="damaged"):
        deface.run(ScanToDeface(subject, (extra,)), options, registration=StandInRegistration())
    assert sorted(path.name for path in tmp_path.iterdir() if path.is_file()) == [
        "inv1.nii",
        "uni.nii.gz",
    ]


def test_a_failure_while_writing_leaves_an_earlier_runs_outputs_untouched(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extra = _save(tmp_path / "inv1.nii", np.arange(120, dtype=np.int16).reshape(6, 5, 4))
    options = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    scan = ScanToDeface(subject, (extra,))
    deface.run(scan, options, registration=StandInRegistration())
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    extra.write_bytes(extra.read_bytes()[:-40])  # the extra is damaged now
    with pytest.raises(OSError, match="damaged"):
        deface.run(scan, options, registration=StandInRegistration())
    after = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    assert set(after) == set(before)  # no temporary files left behind
    assert {k: v for k, v in after.items() if k != "inv1.nii"} == {
        k: v for k, v in before.items() if k != "inv1.nii"
    }


def test_a_crop_that_would_remove_every_slice_of_an_extra_image_is_found_first(tmp_path, template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    high = np.eye(4)
    high[2, 3] = 1000
    extra = _save(tmp_path / "inv1.nii.gz", np.full((6, 5, 4), 3, np.int16), high)
    options = deface.Options(threads=1, template=template)
    with pytest.raises(ValueError, match="remove every slice"):
        deface.run(ScanToDeface(subject, (extra,)), options, registration=StandInRegistration())
    assert [path.name for path in tmp_path.glob("uni_*")] == []


def test_extra_images_on_a_grid_that_differs_only_in_voxel_size_or_codes_get_own_masks(
    tmp_path, template
):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    coded = nib.Nifti1Image(np.full((6, 5, 4), 3, np.int16), np.eye(4))
    coded.set_sform(np.eye(4), code=4)  # same affine, other sform code
    coded_path = tmp_path / "inv1.nii.gz"
    nib.save(coded, coded_path)
    registration = StandInRegistration()
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    deface.run(ScanToDeface(subject, (coded_path,)), options, registration=registration)
    assert len([n for n, _ in registration.moved if "face_mask" in n]) == 2


def test_a_full_disk_while_writing_leaves_the_earlier_outputs_and_no_temporary_files(
    tmp_path, template, monkeypatch
):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 9, np.int16))  # new data
    real_save, saves = deface.nib.save, []

    def failing_save(image, filename):
        saves.append(filename)
        if len(saves) == 5:  # after the stand-in registration and the first outputs
            raise OSError("No space left on device")
        real_save(image, filename)

    monkeypatch.setattr(deface.nib, "save", failing_save)
    with pytest.raises(OSError, match="No space"):
        deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    outputs = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    outputs.pop("uni.nii.gz"), before.pop("uni.nii.gz")
    assert outputs == before  # nothing replaced, no .tmp files


def test_ctrl_c_while_writing_leaves_the_earlier_outputs_and_no_temporary_files(
    tmp_path, template, monkeypatch
):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    options = deface.Options(threads=1, crop=False, qc=False, overwrite=True, template=template)
    deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 9, np.int16))
    real_save, saves = deface.nib.save, []

    def interrupted_save(image, filename):
        saves.append(filename)
        if len(saves) == 5:
            raise KeyboardInterrupt
        real_save(image, filename)

    monkeypatch.setattr(deface.nib, "save", interrupted_save)
    with pytest.raises(KeyboardInterrupt):
        deface.run(ScanToDeface(subject), options, registration=StandInRegistration())
    outputs = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    outputs.pop("uni.nii.gz"), before.pop("uni.nii.gz")
    assert outputs == before


def test_each_extra_image_is_released_before_the_next_one_is_read(tmp_path, template, monkeypatch):
    import gc
    import weakref

    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    extras = tuple(
        _save(tmp_path / f"inv{n}.nii.gz", np.full((6, 5, 4), n, np.int16)) for n in "123"
    )
    real_deface, made = deface.masking.deface, []

    def watching_deface(image, keep):
        gc.collect()
        # made[0] is the main scan, which stays; every extra before this one must be gone
        assert all(ref() is None for ref in made[1:]), "an earlier extra image is still in memory"
        result = real_deface(image, keep)
        made.append(weakref.ref(result))
        return result

    monkeypatch.setattr(deface.masking, "deface", watching_deface)
    options = deface.Options(threads=1, crop=False, qc=False, template=template)
    deface.run(ScanToDeface(subject, extras), options, registration=StandInRegistration())
    assert len(made) == 4
