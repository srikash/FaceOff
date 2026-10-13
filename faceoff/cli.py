"""The `faceoff` command: reads the flags, runs the pipeline for each scan, and reports the result."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from time import monotonic
from typing import Any, TypeVar

import rich_click as click
import rich_click.rich_click as rich_click_config
from rich.console import Group
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text
from rich_click.rich_command import RichCommand

from . import pipeline
from .ants import AntsError, ensure_docker_image
from .console import console, error, format_elapsed, log, quote
from .reporting import ConsoleReporter, package_version, print_banner
from .template import TEMPLATE_CROP_Z, ensure_template

_T = TypeVar("_T")

rich_click_config.OPTION_GROUPS = {
    "*": [
        {
            "name": "Input (-i or --batch required)",
            "options": ["--input", "--batch", "--extra-images"],
            "title_style": "bold red",
        },
        {"name": "Outputs", "options": ["--reorient", "--crop", "--reface"], "title_style": "bold"},
        {
            "name": "Optional flags",
            "options": ["--threads", "--syn", "--version", "--help"],
            "title_style": "bold",
        },
    ]
}
rich_click_config.OPTIONS_TABLE_COLUMN_TYPES = ["opt_short", "opt_long", "metavar", "help"]
rich_click_config.OPTIONS_TABLE_HELP_SECTIONS = ["help", "deprecated", "envvar", "default"]
rich_click_config.TEXT_MARKUP = "rich"

CITATION_NOTICE = (
    "If you use FaceOff, please cite it (Zenodo DOI in the README or CITATION.cff), "
    "the MNI ICBM152 template, and ANTs."
)
_EXAMPLE = "[bold white]faceoff[/] [bold cyan]-i[/] [green]sub-01_T1w.nii.gz[/]"


class FaceOffCommand(RichCommand):
    """Render the usage guide in the same Rich style as the options."""

    def format_epilog(self, context: Any, formatter: Any) -> None:
        def panel(title: str, body: str) -> Padding:
            return Padding(
                Panel(
                    Text.from_markup(body),
                    title=Text.from_markup(f"[bold yellow]{title}[/]"),
                    title_align="left",
                    border_style="yellow",
                    padding=(0, 1),
                ),
                (1, 0, 0, 0),
            )

        content = Group(
            Text.from_markup("[bold orange1]Usage guide:[/]"),
            panel(
                "Deface",
                f"{_EXAMPLE}\n"
                "Writes [green]_defaced[/], [green]_defaceMask[/], [green]_tal_defaced[/] and the "
                "[green]_txn-to-tal[/] transforms next to the input.\n\n"
                f"{_EXAMPLE} [bold cyan]--no-reorient[/]\n"
                "Keeps the original orientation; the transforms are still saved.",
            ),
            panel(
                "Reface",
                f"{_EXAMPLE} [bold cyan]--reface[/]\n"
                "Also writes [green]_refaced[/] and [green]_tal_refaced[/], with the template's "
                "face in place of the removed one.",
            ),
            panel(
                "MP2RAGE or multi-echo GRE",
                f"{_EXAMPLE} [bold cyan]--extra-images[/] "
                "[green]sub-01_inv-1_MP2RAGE.nii.gz,sub-01_inv-2_MP2RAGE.nii.gz[/]\n"
                "Defaces and reorients the other images with the same mask, using the "
                "registration of the [bold cyan]-i[/] scan.",
            ),
            panel(
                "Batch",
                "[bold white]faceoff[/] [bold cyan]--batch[/] "
                "[green]sub-01_T1w.nii.gz,sub-02_T1w.nii.gz[/]\n"
                "Processes the scans one after another.",
            ),
            Text.from_markup(f"\n[dim]{CITATION_NOTICE}[/]"),
        )
        formatter.write(Padding(content, formatter.config.padding_epilog))


def _resolve_threads(threads: int | None) -> int:
    """--threads, then ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS, then every core."""
    if threads is not None:
        return threads
    if env_threads := os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        return int(env_threads)
    return os.cpu_count() or 1


def _with_elapsed_ticker(work: Callable[[], _T]) -> _T:
    """Run `work()` while a "Time elapsed" line updates below the log (terminals only)."""
    if not console.is_terminal:
        return work()
    result: list[_T] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            result.append(work())
        except BaseException as exc:  # re-raised on the calling thread below
            failure.append(exc)

    started = monotonic()
    thread = Thread(target=target, daemon=True)
    thread.start()
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        try:
            while thread.is_alive():
                elapsed = format_elapsed(monotonic() - started)
                live.update(Text(f"Time elapsed: {elapsed}", style="dim"))
                thread.join(timeout=0.2)
        except KeyboardInterrupt:
            # Ctrl-C also stops the running ANTs container; let the worker clean up its
            # scratch folder before exiting.
            thread.join()
            raise
    if failure:
        raise failure[0]
    return result[0]


@click.command(
    name="faceoff",
    cls=FaceOffCommand,
    help=(
        "Deface anatomical MRI scans using ANTs in Docker, with optional reorientation to "
        "MNI152 template space and optional refacing."
    ),
    epilog=CITATION_NOTICE,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "-i", "--input", "input_file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="The scan to deface (.nii or .nii.gz).",
)
@click.option("--batch", help="Several scans separated by commas, processed one after another.")
@click.option(
    "--extra-images", multiple=True, metavar="FILES",
    help="Other images in the same scanner space as -i (for example MP2RAGE INV1, INV2 and "
    "UNI, or GRE echoes; 4D is fine), separated by commas. They get the same deface mask and "
    "reorientation, but are not refaced. Not with --batch.",
)
@click.option(
    "--reorient/--no-reorient", default=True, show_default=True,
    help="Also write the defaced scan in template orientation (header only, no resampling). "
    "The ITK and FSL transforms are saved either way.",
)
@click.option(
    "--crop/--no-crop", default=True, show_default=True,
    help=f"Trim the reoriented scan to template slices {TEMPLATE_CROP_Z[0]} to "
    f"{TEMPLATE_CROP_Z[1] - 1} along z. Whole slices are dropped; nothing is resampled.",
)
@click.option(
    "--reface", is_flag=True,
    help="Also write a refaced scan, with the template's face in place of the removed one.",
)
@click.option(
    "-n", "--threads", type=click.IntRange(min=1), default=None, metavar="N",
    help="Threads for ANTs. Default: ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS, else every core.",
)
@click.option(
    "--syn", is_flag=True,
    help="Not required; included for completeness. Adds a slower registration and uses it "
    "for the deface mask. The default registration already gives almost the same mask.",
)
@click.option("-d", "depad", is_flag=True, hidden=True, help="Deprecated; ignored.")
@click.version_option(package_version(), "--version", prog_name="faceoff")
def cli(
    input_file: Path | None,
    batch: str | None,
    extra_images: tuple[str, ...],
    reorient: bool,
    crop: bool,
    reface: bool,
    threads: int | None,
    syn: bool,
    depad: bool,
) -> None:
    """Deface one scan, or several with --batch."""
    if (input_file is None) == (batch is None):
        raise click.UsageError("Give exactly one of -i/--input or --batch.")
    extras = tuple(Path(p.strip()) for item in extra_images for p in item.split(",") if p.strip())
    if extras and batch:
        raise click.UsageError("--extra-images belongs to one scan; use it with -i, not --batch.")
    for extra in extras:
        if not extra.is_file():
            raise click.BadParameter(f"File '{extra}' does not exist.", param_hint="--extra-images")
    files = (
        [Path(p.strip()) for p in batch.split(",") if p.strip()] if batch else [input_file]
    )

    print_banner()
    if depad:
        log("[yellow]-d (depadding) is deprecated and ignored.[/]")
    try:
        ensure_docker_image()
        ensure_template(log=log)
    except RuntimeError as failure:
        error(str(failure))
        raise SystemExit(1) from failure

    options = pipeline.Options(
        threads=_resolve_threads(threads), syn=syn, reorient=reorient, crop=crop, reface=reface,
        extra_images=extras,
    )
    if len(files) > 1:
        quote("This is turning into a real marriage.", "Face/Off (1997)")
        console.print()

    failed = []
    for path in files:
        try:
            _with_elapsed_ticker(lambda: pipeline.run(path, options, ConsoleReporter()))
        except AntsError as failure:
            error(f"{path}: {failure}")
            failed.append(path)
        except (FileNotFoundError, ValueError) as failure:
            error(str(failure))
            failed.append(path)
    if failed:
        error(f"{len(failed)} of {len(files)} scans failed.")
        raise SystemExit(1)
    console.print(f"[dim]{CITATION_NOTICE}[/]")


def main() -> None:
    cli()
