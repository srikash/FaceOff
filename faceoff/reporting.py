"""Console progress for the CLI: a version banner, timestamped steps, and a closing summary."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import monotonic

from .ants import ANTS_IMAGE
from .console import console, format_elapsed, log, quote, success
from .pipeline import Options, Outputs
from .reorient import Crop
from .template import TEMPLATE_CROP_Z, TEMPLATE_DIR


def package_version() -> str:
    """The installed FaceOff version, or "dev" when run from a source checkout."""
    try:
        return version("faceoff")
    except PackageNotFoundError:
        return "dev"


def print_banner() -> None:
    title = f"faceoff v{package_version()}"
    width = max(len(title) + 4, 45)
    border = "%" + "-" * (width - 2) + "%"
    console.print(f"[bold cyan]{border}[/bold cyan]")
    console.print(f"[bold cyan]{title.center(width)}[/bold cyan]")
    console.print(f"[bold cyan]{border}[/bold cyan]")


class ConsoleReporter:
    """Prints one image's progress: what will be written, each finished step, and the outputs."""

    def __init__(self) -> None:
        self._outputs: Outputs | None = None
        self._start = self._last = 0.0

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None:
        self._outputs = outputs
        self._start = self._last = monotonic()
        yes_no = {True: "[green]yes[/]", False: "[dim]no[/]"}
        console.print(f"[bold]Input:[/bold] {input_file}", soft_wrap=True)
        console.print(f"[bold]Template:[/bold] {TEMPLATE_DIR}", soft_wrap=True)
        console.print(f"[bold]ANTs:[/bold] {ANTS_IMAGE} ({options.threads} threads)")
        console.print(
            f"[bold]Reorient:[/bold] {yes_no[options.reorient]}   "
            f"[bold]Crop (z {TEMPLATE_CROP_Z[0]}-{TEMPLATE_CROP_Z[1] - 1}):[/bold] "
            f"{yes_no[options.crop and options.reorient]}   "
            f"[bold]Reface:[/bold] {yes_no[options.reface]}   "
            f"[bold]SyN:[/bold] {yes_no[options.syn]}"
        )
        console.print()

    def registering(self, syn: bool, reface: bool) -> None:
        quote("It's like looking in a mirror, only… not.", "Face/Off (1997)")
        if syn or reface:
            console.print()
            quote(
                "Looks like you're going to be in here for the next hundred years.",
                "Face/Off (1997)",
            )
        console.print()
        log("Started: registration to the template")

    def step(self, message: str) -> None:
        now = monotonic()
        log(f"Completed: {message} in {format_elapsed(now - self._last)}")
        self._last = now

    def cropped(self, crop: Crop) -> None:
        log(
            f"Cropped to native slices {crop.first}-{crop.last - 1} of {crop.size} "
            f"along voxel axis {crop.axis}"
        )

    def end(self) -> None:
        success(f"Finished in {format_elapsed(monotonic() - self._start)}")
        if self._outputs is not None:
            for path in self._outputs.written():
                shown = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
                console.print(f"  [green]✓[/green] {shown}", soft_wrap=True)
        console.print()
