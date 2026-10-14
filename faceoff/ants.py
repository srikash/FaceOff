"""Run ANTs tools from the antsx/ants Docker image, so ANTs need not be installed.

`DockerAnts` runs the real tools; `RecordingAnts` only writes the commands down, for the
tests. Each folder named in a command is made visible inside the container at the same path,
so commands look exactly as they would with a local ANTs. The container can only write to
the run's temporary folder.
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
    """Anything that can run an ANTs tool (DockerAnts for real runs, RecordingAnts in tests)."""

    def run(self, tool: str, args: Sequence[str | Path]) -> None:
        """Run `tool` (for example "antsRegistration") with `args`. Raises AntsError if it
        fails."""


class DockerAnts:
    """Run ANTs tools in the pinned Docker image, starting one container per tool.

    Files ANTs writes belong to you, not to root (on Linux and macOS).
    """

    def __init__(self, threads: int, scratch: Path, image: str = ANTS_IMAGE) -> None:
        self.threads = threads
        self.scratch = scratch
        self.image = image

    def command(self, tool: str, args: Sequence[str | Path]) -> list[str]:
        """Return the full `docker run` command for one ANTs tool."""
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
        """Run `tool` with `args` in Docker. Raises AntsError if it fails."""
        returncode = subprocess.run(self.command(tool, args)).returncode
        if returncode != 0:
            raise AntsError(f"{tool} failed (exit code {returncode}).")


def _mounts(args: Sequence[str | Path], scratch: Path) -> list[tuple[Path, bool]]:
    """Return the folders the container needs: the temporary folder (writable), and the
    folder of every file named in the command, including inside ANTs brackets such as
    `MI[a,b,1,32]` (read-only). A folder inside one already listed is skipped, because Docker
    refuses to mount the same place twice."""
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
    """For tests: writes each ANTs command down instead of running it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def run(self, tool: str, args: Sequence[str | Path]) -> None:
        """Note down `tool` and `args` in `calls`."""
        self.calls.append((tool, [str(a) for a in args]))


def ensure_docker_image(image: str = ANTS_IMAGE) -> None:
    """Check that Docker works and the ANTs image is there, downloading it if needed.

    Raises RuntimeError if Docker is missing or the image cannot be downloaded.
    """
    if shutil.which("docker") is None:
        raise RuntimeError("Docker not found. FaceOff runs ANTs from the Docker image " + image)
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0:
        return
    if subprocess.run(["docker", "pull", image]).returncode != 0:
        raise RuntimeError(f"Could not pull {image}. Is the Docker daemon running?")
