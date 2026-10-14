"""A small synthetic template that tests can pass to FaceOff instead of the real one."""

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from faceoff.template import Template


def write_template(folder: Path, affine: np.ndarray | None = None, shape=(8, 8, 8)) -> Template:
    """Write the five template files (tiny, filled with simple values) into `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    template = Template(folder)
    affine = np.eye(4) if affine is None else affine
    brain = np.zeros(shape, np.uint8)
    brain[2:-2, 2:-2, 2:-2] = 1
    for path, data in [
        (template.t1w, np.full(shape, 20, np.int16)),
        (template.brain_mask, brain),
        (template.reface_mask, np.ones(shape, np.uint8)),
        (template.face_mask, np.zeros(shape, np.uint8)),
        (template.eye_mask, np.zeros(shape, np.uint8)),
    ]:
        nib.save(nib.Nifti1Image(data, affine), path)
    return template


@pytest.fixture(autouse=True)
def no_local_ants_unless_a_test_says_so(monkeypatch):
    """Tests must not depend on whether this machine has ANTs on its PATH."""
    monkeypatch.setattr("faceoff.ants.local_ants_available", lambda: False)


@pytest.fixture
def template(tmp_path) -> Template:
    """A 1 mm synthetic template in a temporary folder."""
    return write_template(tmp_path / "template")
