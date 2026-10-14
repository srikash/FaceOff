"""Everything FaceOff prints in the terminal: the banner, timestamped steps, and the summary."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import monotonic

from rich.console import Console

from .deface import Options, Outputs, Reporter
from .reorient import Crop
from .template import TEMPLATE_CROP_Z_MM

console = Console()


def log(message: str) -> None:
    """Print a progress line with the current UTC time in front of it."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    console.print(f"[dim]{now}[/] {message}", soft_wrap=True)  # soft_wrap: keep paths on one line


def success(message: str) -> None:
    """Print a green tick and `message`."""
    console.print(f"[bold green]✓[/bold green] {message}", soft_wrap=True)


def error(message: str) -> None:
    """Print a red cross and `message`."""
    console.print(f"[bold red]✗[/bold red] {message}", soft_wrap=True)


def quote(text: str, source: str) -> None:
    """Print a quotation in italics, with its source on the next line."""
    console.print(f'  [italic]"{text}"[/]')
    console.print(f"      [dim]{source}[/]")


def format_elapsed(seconds: float) -> str:
    """Return a short duration: "6.4s" under a minute, otherwise "3m 15s"."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(int(seconds), 60)
    return f"{minutes}m {remaining}s"


def package_version() -> str:
    """Return the installed FaceOff version, or "dev" when run from a source checkout."""
    try:
        return version("faceoff")
    except PackageNotFoundError:
        return "dev"


def print_banner() -> None:
    """Print the opening banner: the name and version between two rules."""
    title = f"faceoff v{package_version()}"
    width = max(len(title) + 4, 45)
    border = "%" + "-" * (width - 2) + "%"
    console.print(f"[bold cyan]{border}[/bold cyan]")
    console.print(f"[bold cyan]{title.center(width)}[/bold cyan]")
    console.print(f"[bold cyan]{border}[/bold cyan]")


class ConsoleReporter(Reporter):
    """Prints one scan's progress: the settings, each finished step, and the files written."""

    def __init__(self) -> None:
        self._outputs: Outputs | None = None
        self._start = self._last = 0.0

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None:
        """Print the input, template, ANTs image, and chosen options, then start the clock."""
        self._outputs = outputs
        self._start = self._last = monotonic()
        yes_no = {True: "[green]yes[/]", False: "[dim]no[/]"}
        console.print(f"[bold]Input:[/bold] {input_file}", soft_wrap=True)
        console.print(f"[bold]Template:[/bold] {options.template.folder}", soft_wrap=True)
        console.print(
            f"[bold]ANTs:[/bold] {options.container.describe()} ({options.threads} threads)",
            soft_wrap=True,
        )
        console.print(
            f"[bold]Reorient:[/bold] {yes_no[options.reorient]}   "
            f"[bold]Crop (z {TEMPLATE_CROP_Z_MM[0]:g} to {TEMPLATE_CROP_Z_MM[1]:g} mm):[/bold] "
            f"{yes_no[options.crop and options.reorient]}   "
            f"[bold]Reface:[/bold] {yes_no[options.reface]}   "
            f"[bold]Enucleate:[/bold] {yes_no[options.remove_eyes]}   "
            f"[bold]Renucleate:[/bold] {yes_no[options.put_back_eyes]}   "
            f"[bold]QC:[/bold] {yes_no[options.qc]}   "
            f"[bold]SyN:[/bold] {yes_no[options.syn]}"
        )
        console.print()
        quote("It's like looking in a mirror, only… not.", "Face/Off (1997)")
        if options.syn or options.refill:
            console.print()
            quote(
                "Looks like you're going to be in here for the next hundred years.",
                "Face/Off (1997)",
            )
        console.print()
        log("Started: registration to the template")

    def step(self, message: str) -> None:
        """Print that a step finished, and how long it took."""
        now = monotonic()
        log(f"Completed: {message} in {format_elapsed(now - self._last)}")
        self._last = now

    def warn(self, message: str) -> None:
        """Print a problem that did not stop the run."""
        log(f"[yellow]{message}[/]")

    def cropped(self, crop: Crop) -> None:
        """Print which of the scan's own slices were kept."""
        log(
            f"Cropped to native slices {crop.first}-{crop.last - 1} of {crop.size} "
            f"along voxel axis {crop.axis}"
        )

    def end(self) -> None:
        """Print the total time and a tick for every file written."""
        success(f"Finished in {format_elapsed(monotonic() - self._start)}")
        if self._outputs is not None:
            for path in filter(Path.exists, self._outputs.written()):
                shown = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
                console.print(f"  [green]✓[/green] {shown}", soft_wrap=True)
        console.print()
