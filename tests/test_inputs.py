"""Checking the scans, extra images, and thread count before anything runs."""

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from faceoff.inputs import InputError, ScanToDeface, ants_threads, scans_to_deface, strip_extension


def _touch(path):
    """Write a tiny real NIfTI image (the inputs are checked for being readable)."""
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2), np.int16), np.eye(4)), path)
    return path


def test_scans_and_extra_images_come_back_with_full_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "uni.nii.gz")
    _touch(tmp_path / "inv1.nii")
    [scan] = scans_to_deface([tmp_path / "uni.nii.gz"], [tmp_path / "inv1.nii"])
    assert scan == ScanToDeface(tmp_path / "uni.nii.gz", (tmp_path / "inv1.nii",))


def test_every_problem_is_reported_at_once(tmp_path):
    _touch(tmp_path / "uni.nii.gz")
    (tmp_path / "notes.txt").write_text("not an image")
    with pytest.raises(InputError) as problems:
        scans_to_deface(
            [tmp_path / "uni.nii.gz", tmp_path / "missing.nii.gz", tmp_path / "notes.txt"],
            [tmp_path / "nope.nii.gz"],
        )
    message = str(problems.value)
    assert "Scan not found" in message and "missing.nii.gz" in message
    assert "Unsupported extension: notes.txt" in message
    assert "Extra image not found" in message and "nope.nii.gz" in message


def test_a_file_that_is_not_a_readable_nifti_image_is_reported_for_scans_and_extras(tmp_path):
    good = _touch(tmp_path / "uni.nii.gz")
    empty = tmp_path / "empty.nii.gz"
    empty.write_bytes(b"")
    with pytest.raises(InputError) as problems:
        scans_to_deface([good, empty], [empty.with_name("also_empty.nii")])
    message = str(problems.value)
    assert "Scan cannot be read as a NIfTI image: empty.nii.gz" in message
    assert "Extra image not found" in message


def test_the_scan_is_not_one_of_its_own_extra_images(tmp_path):
    scan = _touch(tmp_path / "uni.nii.gz")
    with pytest.raises(InputError, match="input itself"):
        scans_to_deface([scan], [scan])


def test_strip_extension():
    assert strip_extension(Path("a/scan.nii.gz")).name == "scan"
    assert strip_extension(Path("scan.nii")).name == "scan"
    with pytest.raises(InputError):
        strip_extension(Path("scan.mgz"))


@pytest.mark.parametrize(
    ("given", "environment", "expected"),
    [
        (4, {"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": "8"}, 4),  # --threads wins
        (None, {"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": "8"}, 8),
    ],
)
def test_thread_count(given, environment, expected):
    assert ants_threads(given, environment) == expected


@pytest.mark.parametrize("value", ["lots", "0", "-2", "2.5"])
def test_a_thread_count_that_is_not_a_whole_number_is_refused(value):
    with pytest.raises(InputError, match="whole number"):
        ants_threads(None, {"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": value})
