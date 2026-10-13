"""The template files and how to fetch them. Standard library only, so the build hook can use it."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from collections.abc import Callable
from pathlib import Path

ZENODO_RECORD = "23328835"
PREFIX = "faceoff2_mni152_version-ext2020sym_desc-"

# File name -> md5, as published on https://zenodo.org/records/23328835
TEMPLATE_FILES = {
    f"{PREFIX}T1w_ref.nii.gz": "b96f7d55213cf2164ac90332b4c4b0ee",
    f"{PREFIX}brain_mask.nii.gz": "e83d203ab5d42ba09dcf7c251ffb8a71",
    f"{PREFIX}reface_mask.nii.gz": "621a213af921a0987a42bd7c38d7547e",
    f"{PREFIX}face_mask.nii.gz": "44e883687d0cccd494769a48c416dcc6",
}


def md5(path: Path) -> str:
    """Hex md5 of a file, read in 1 MB chunks."""
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_complete(directory: Path) -> bool:
    """True when every template file is present and matches its published checksum."""
    return all(_valid(directory / name, checksum) for name, checksum in TEMPLATE_FILES.items())


def _valid(path: Path, checksum: str) -> bool:
    return path.is_file() and md5(path) == checksum


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)


def fetch_missing(
    directory: Path,
    download: Callable[[str, Path], None] = _download,
    log: Callable[[str], None] = lambda message: None,
) -> None:
    """Download any missing or corrupt template file from Zenodo into `directory`.

    Raises RuntimeError on a network failure or checksum mismatch.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, checksum in TEMPLATE_FILES.items():
        target = directory / name
        if _valid(target, checksum):
            continue
        url = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/{name}/content"
        log(f"Downloading template file {name} from Zenodo record {ZENODO_RECORD} ...")
        partial = target.with_name(target.name + ".part")
        try:
            download(url, partial)
            if md5(partial) != checksum:
                raise RuntimeError(f"Checksum mismatch for {name} downloaded from {url}")
            partial.replace(target)
        except OSError as err:
            raise RuntimeError(f"Could not download {name} from {url}: {err}") from err
        finally:
            partial.unlink(missing_ok=True)
