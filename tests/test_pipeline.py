"""pipeline.run end to end, with a fake ANTs adapter that writes plausible outputs."""


import nibabel as nib
import numpy as np
import pytest

from faceoff import pipeline, reorient


class FakeAnts:
    """Writes the files the pipeline reads back: a warped face mask (face = x < 2 on the
    reference grid) and an identity affine. Registration calls do nothing."""

    def __init__(self) -> None:
        self.references: list[str] = []

    def run(self, tool, args):
        args = [str(a) for a in args]
        if tool == "antsApplyTransforms":
            reference = nib.load(args[args.index("--reference-image") + 1])
            self.references.append(args[args.index("--reference-image") + 1])
            face = np.zeros(reference.shape[:3], np.uint8)
            face[:2] = 1
            nib.save(nib.Nifti1Image(face, reference.affine), args[args.index("--output") + 1])
        elif tool == "ConvertTransformFile":
            np.savetxt(args[2], np.eye(4))


@pytest.fixture
def no_template(monkeypatch, tmp_path):
    ref = tmp_path / "ref.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), np.int16), np.eye(4)), ref)
    monkeypatch.setattr(reorient, "TEMPLATE_REF", ref)
    monkeypatch.setattr(reorient, "brain_centre_lps", lambda: np.zeros(3))


def _save(path, data, affine=None):
    nib.save(nib.Nifti1Image(data, np.eye(4) if affine is None else affine), path)
    return path


def test_extra_images_and_tal_mask(tmp_path, no_template):
    subject = _save(tmp_path / "uni.nii.gz", np.full((6, 5, 4), 7, np.int16))
    other_grid = _save(  # same space, half the resolution
        tmp_path / "inv1.nii.gz", np.full((3, 5, 4), 5, np.int16), np.diag([2.0, 1, 1, 1])
    )
    echoes = _save(tmp_path / "gre.nii.gz", np.full((6, 5, 4, 3), 9, np.int16))
    options = pipeline.Options(threads=1, crop=False, extra_images=(other_grid, echoes))
    ants = FakeAnts()

    outputs = pipeline.run(subject, options, ants=ants)

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
    assert ants.references[2].endswith("extra1_grid.nii.gz")


def test_input_is_not_an_extra_image(tmp_path, no_template):
    subject = _save(tmp_path / "uni.nii.gz", np.zeros((2, 2, 2), np.int16))
    options = pipeline.Options(threads=1, extra_images=(subject,))
    with pytest.raises(ValueError, match="input itself"):
        pipeline.run(subject, options, ants=FakeAnts())
