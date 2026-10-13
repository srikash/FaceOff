"""Run ANTs tools from the antsx/ants Docker image.

The seam is `AntsRunner`: `DockerAnts` runs the real tools, `RecordingAnts` records the commands
for tests. `DockerAnts` mounts every folder named in the arguments at the same location inside
the container, so arguments pass through unchanged. Only the scratch folder is writable.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

ANTS_IMAGE = "antsx/ants:2.6.5"


class AntsError(RuntimeError):
    """An ANTs tool exited with an error."""


class AntsRunner(Protocol):
    def run(self, tool: str, args: Sequence[str | Path]) -> None: ...


class DockerAnts:
    def __init__(self, threads: int, scratch: Path, image: str = ANTS_IMAGE) -> None:
        self.threads = threads
        self.scratch = scratch
        self.image = image

    def command(self, tool: str, args: Sequence[str | Path]) -> list[str]:
        cmd = [
            "docker", "run", "--rm",
            "--init",  # lets Ctrl-C reach ANTs
            "--security-opt", "label=disable",  # SELinux hosts block bind mounts otherwise
            "-e", f"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS={self.threads}",
        ]
        if hasattr(os, "getuid"):  # outputs owned by the caller, not root
            cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
        for folder, writable in _mounts(args, self.scratch):
            # --mount, not -v: scratch paths contain colons
            spec = f"type=bind,source={folder},target={folder}"
            cmd += ["--mount", spec if writable else f"{spec},readonly"]
        return [*cmd, self.image, tool, *(str(a) for a in args)]

    def run(self, tool: str, args: Sequence[str | Path]) -> None:
        returncode = subprocess.run(self.command(tool, args)).returncode
        if returncode != 0:
            raise AntsError(f"{tool} failed (exit code {returncode}).")


def _mounts(args: Sequence[str | Path], scratch: Path) -> list[tuple[Path, bool]]:
    """Folders to mount: the scratch folder (writable) plus the folder of every absolute path
    in the arguments, including those inside ANTs brackets such as `MI[a,b,1,32]` (read-only).
    Folders inside an already mounted folder are skipped; Docker rejects duplicate targets."""
    folders = set()
    for arg in args:
        for token in re.split(r"[\[\],]", str(arg)):
            if token.startswith("/"):
                path = Path(token)
                folders.add(path if path.is_dir() else path.parent)
    chosen = [(scratch, True)]
    for folder in sorted(folders, key=lambda f: (len(f.parts), str(f))):
        if not any(folder.is_relative_to(done) for done, _ in chosen):
            chosen.append((folder, False))
    return chosen


class RecordingAnts:
    """Test adapter: records the commands instead of running them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def run(self, tool: str, args: Sequence[str | Path]) -> None:
        self.calls.append((tool, [str(a) for a in args]))


def ensure_docker_image(image: str = ANTS_IMAGE) -> None:
    """Raise RuntimeError unless Docker works and the image is available (pulling if needed)."""
    if shutil.which("docker") is None:
        raise RuntimeError("Docker not found. FaceOff runs ANTs from the Docker image " + image)
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0:
        return
    if subprocess.run(["docker", "pull", image]).returncode != 0:
        raise RuntimeError(f"Could not pull {image}. Is the Docker daemon running?")
