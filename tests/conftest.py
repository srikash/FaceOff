"""For the tests: a small synthetic template, and a stand-in registration that moves template
images onto a scan with a known affine instead of running ANTs."""

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from faceoff.registration import Stage
from faceoff.template import Template

_LPS_FLIP = np.diag([-1.0, -1.0, 1.0, 1.0])


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


class StandInRegistration:
    """A registration for the tests: no ANTs, just a known affine.

    `template_to_scan` (4x4, RAS, mm) takes template points to scan points; by default the
    template and the scan are aligned. `per_stage` adds an extra 4x4 for a stage, applied after
    it, so a test can give two warps different results. Template images are moved onto the
    scan's grid (or another image's) by nearest neighbour, which is exact for masks.
    `moved` keeps (template file name, stage) for every image moved.
    """

    def __init__(self, template_to_scan: np.ndarray | None = None,
                 per_stage: dict[Stage, np.ndarray] | None = None) -> None:
        self.template_to_scan = np.eye(4) if template_to_scan is None else template_to_scan
        self.per_stage = per_stage or {}
        self.moved: list[tuple[str, Stage]] = []
        self._subject: Path | None = None

    def __call__(self, ws, subject: Path, options) -> "StandInRegistration":
        """Stands in for deface.register_with_ants."""
        self._subject = subject
        return self

    @property
    def affine_lps(self) -> np.ndarray:
        return _LPS_FLIP @ self.template_to_scan @ _LPS_FLIP

    def to_subject(self, template_image, output, stage, interpolation="GenericLabel",
                   reference=None) -> None:
        self.moved.append((Path(template_image).name, stage))
        grid = nib.load(reference or self._subject)
        source = nib.load(template_image)
        data = np.asanyarray(source.dataobj)
        mapping = self.per_stage.get(stage, np.eye(4)) @ self.template_to_scan
        shape = grid.shape[:3]
        voxels = np.vstack([np.indices(shape).reshape(3, -1), np.ones(np.prod(shape))])
        found = np.linalg.inv(source.affine) @ np.linalg.inv(mapping) @ grid.affine @ voxels
        found = np.rint(found[:3]).astype(int)
        inside = np.all((found >= 0) & (found < np.array(data.shape)[:, None]), axis=0)
        moved = np.zeros(int(np.prod(shape)), np.float32)
        moved[inside] = data[tuple(found[:, inside])]
        nib.save(nib.Nifti1Image(moved.reshape(shape), grid.affine), output)
