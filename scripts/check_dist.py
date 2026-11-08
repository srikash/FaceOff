"""Check the built package: usage `python scripts/check_dist.py dist/`.

The wheel must carry the five template files and the MNI notice, and the source archive must
not carry scratch folders, test scans or the downloaded template (the wheel build downloads
it again). Uses only the standard library, so CI can run it anywhere.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

TEMPLATE_PREFIX = "faceoff2_mni152_version-ext2020sym_desc-"
TEMPLATE_PARTS = ("T1w_ref", "brain_mask", "reface_mask", "face_mask", "eye_mask")
NEVER_IN_THE_SDIST = ("testdata/", "tempData/", "faceoff/data/", "HANDOFF", "registration_review/")


def problems(dist: Path) -> list[str]:
    found: list[str] = []
    wheels, sdists = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return [
            f"expected one wheel and one sdist in {dist}, found {len(wheels)} and {len(sdists)}"
        ]

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
    for part in TEMPLATE_PARTS:
        if f"faceoff/data/{TEMPLATE_PREFIX}{part}.nii.gz" not in names:
            found.append(f"wheel is missing the template file {part}")
    if "faceoff/COPYING-MNI" not in names:
        found.append("wheel is missing faceoff/COPYING-MNI")
    if "faceoff/cli.py" not in names:
        found.append("wheel is missing the program itself")

    with tarfile.open(sdists[0]) as sdist:
        members = sdist.getnames()
    for member in members:
        relative = member.split("/", 1)[-1]
        if relative.startswith(NEVER_IN_THE_SDIST) or relative.endswith((".nii", ".nii.gz")):
            found.append(f"source archive contains {relative}")
    for needed in ("bundle_template.py", "faceoff/template_files.py", "uv.lock"):
        if not any(member.endswith("/" + needed) for member in members):
            found.append(f"source archive is missing {needed}")
    return found


def main() -> int:
    issues = problems(Path(sys.argv[1] if len(sys.argv) > 1 else "dist"))
    for issue in issues:
        print(f"PROBLEM: {issue}")
    print("package contents look right" if not issues else f"{len(issues)} problem(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
