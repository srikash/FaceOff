"""scripts/check_dist.py, which CI and the release use to check the built package."""

import importlib.util
import tarfile
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_dist", Path(__file__).resolve().parent.parent / "scripts" / "check_dist.py"
)
assert SPEC is not None and SPEC.loader is not None
check_dist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_dist)


def _build(folder: Path, wheel_files: list[str], sdist_files: list[str]) -> Path:
    folder.mkdir()
    with zipfile.ZipFile(folder / "p-1-py3-none-any.whl", "w") as wheel:
        for name in wheel_files:
            wheel.writestr(name, "x")
    with tarfile.open(folder / "p-1.tar.gz", "w:gz") as sdist:
        for name in sdist_files:
            source = folder / "member"
            source.write_text("x")
            sdist.add(source, arcname=f"p-1/{name}")
    return folder


GOOD_WHEEL = [
    f"faceoff/data/{check_dist.TEMPLATE_PREFIX}{part}.nii.gz" for part in check_dist.TEMPLATE_PARTS
] + ["faceoff/COPYING-MNI", "faceoff/cli.py"]
GOOD_SDIST = ["bundle_template.py", "faceoff/template_files.py", "uv.lock", "faceoff/cli.py"]


def test_a_complete_package_passes(tmp_path):
    assert check_dist.problems(_build(tmp_path / "d", GOOD_WHEEL, GOOD_SDIST)) == []


def test_a_wheel_without_the_template_is_caught(tmp_path):
    dist = _build(tmp_path / "d", GOOD_WHEEL[2:], GOOD_SDIST)
    assert any("missing the template file" in issue for issue in check_dist.problems(dist))


def test_scans_and_scratch_folders_in_the_source_archive_are_caught(tmp_path):
    dist = _build(tmp_path / "d", GOOD_WHEEL, [*GOOD_SDIST, "testdata/head.nii.gz", "tempData/x"])
    issues = check_dist.problems(dist)
    assert any("testdata/head.nii.gz" in issue for issue in issues)
    assert any("tempData/x" in issue for issue in issues)
