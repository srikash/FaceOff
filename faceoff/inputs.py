"""Check every scan, extra image, and the thread count before anything runs.

`scans_to_deface` is the only place input files are checked. It looks at all of them first and
reports every problem at once, so a mistyped name in a long --batch is found before the first
scan is registered, not after.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class InputError(ValueError):
    """A problem with the files or numbers given. Nothing has run yet."""


@dataclass(frozen=True)
class ScanToDeface:
    """One scan to deface, with the other images from its session (full paths, checked)."""

    scan: Path
    extra_images: tuple[Path, ...] = ()


def strip_extension(path: Path) -> Path:
    """Return the file name without .nii or .nii.gz (`scan.nii.gz` becomes `scan`).

    Raises InputError for any other file type.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return path.parent / name[:-7]
    if name.endswith(".nii"):
        return path.parent / name[:-4]
    raise InputError(f"Unsupported extension: {path.name}. Must be .nii or .nii.gz")


def scans_to_deface(
    scans: Sequence[Path], extra_images: Sequence[Path] = ()
) -> list[ScanToDeface]:
    """Check the scans (one with -i, several with --batch) and the extra images that go with
    a single scan, and return them with full paths.

    Every file must exist and be .nii or .nii.gz, and a scan must not also be listed as one of
    its extra images. Raises InputError listing every problem found.
    """
    problems: list[str] = []

    def check(path: Path, kind: str) -> Path:
        full = path.resolve()
        if not full.is_file():
            problems.append(f"{kind} not found: {full}")
        else:
            try:
                strip_extension(full)
            except InputError as problem:
                problems.append(str(problem))
        return full

    checked = [check(scan, "Scan") for scan in scans]
    extras = tuple(check(extra, "Extra image") for extra in extra_images)
    for extra in extras:
        if extra in checked:
            problems.append(f"{extra.name} is the input itself; do not list it in extra images.")
    if problems:
        raise InputError("\n".join(problems))
    return [ScanToDeface(scan, extras) for scan in checked]


def ants_threads(threads: int | None, environ: Mapping[str, str] = os.environ) -> int:
    """Return how many threads ANTs may use: `threads` (--threads) if given, otherwise
    ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS if set, otherwise every core.

    Raises InputError if the environment variable is not a whole number of 1 or more.
    """
    if threads is not None:
        return threads
    if value := environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        if not value.strip().isdigit() or int(value) < 1:
            raise InputError(
                f"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS is {value!r}; it must be a whole number "
                "of 1 or more."
            )
        return int(value)
    return os.cpu_count() or 1
