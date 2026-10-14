"""The `faceoff` command: reads the options, defaces each scan, and reports what happened."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import rich_click as click
import rich_click.rich_click as rich_click_config
from rich import box
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich_click.rich_command import RichCommand

from . import deface
from .ants import AntsError, ensure_docker_image
from .messages import (
    ConsoleReporter,
    console,
    error,
    log,
    package_version,
    print_banner,
    quote,
)
from .template import TEMPLATE_CROP_Z, ensure_template

# The two ways of giving input get their own colour, here and in the usage guide.
_ONE_SCAN = "cyan"
_BATCH = "magenta"

rich_click_config.OPTION_GROUPS = {
    "*": [
        {
            "name": "Input A: one scan (-i)",
            "help": "One registration, shared by -i and its extra images. Use A or B, not both.",
            "options": ["--input", "--extra-images"],
            "title_style": f"bold {_ONE_SCAN}",
            "panel_styles": {"border_style": _ONE_SCAN},
        },
        {
            "name": "Input B: several scans (--batch)",
            "help": "A separate registration for every scan. Use A or B, not both.",
            "options": ["--batch"],
            "title_style": f"bold {_BATCH}",
            "panel_styles": {"border_style": _BATCH},
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
_MP2RAGE_EXAMPLE = "[bold white]faceoff[/] [bold cyan]-i[/] [green]sub-01_UNIT1.nii.gz[/]"


class FaceOffCommand(RichCommand):
    """The `faceoff` command, with a usage guide drawn in the same style as the options."""

    def format_epilog(self, context: Any, formatter: Any) -> None:
        """Draw the usage guide (example commands in yellow boxes) below the options."""
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
                "Writes [green]_defaced[/], [green]_defaceMask[/], [green]_tal_defaced[/], "
                "[green]_tal_defaceMask[/], and the [green]_txn-to-tal[/] transforms next to "
                "the input.\n\n"
                f"{_EXAMPLE} [bold cyan]--no-reorient[/]\n"
                "Keeps the original orientation; the transforms are still saved.",
            ),
            panel(
                "Reface",
                f"{_EXAMPLE} [bold cyan]--reface[/]\n"
                "Also writes [green]_refaced[/] and [green]_tal_refaced[/], with the template's "
                "face in place of the removed one.",
            ),
            _extra_images_or_batch(),
            panel(
                "Many MP2RAGE or GRE sessions",
                "--batch cannot take extra images, so run FaceOff once per session, for "
                "example in a loop:\n"
                "[bold white]for[/] uni [bold white]in[/] [green]sub-*_UNIT1.nii.gz[/]; "
                "[bold white]do[/]\n"
                "  [bold white]faceoff[/] [bold cyan]-i[/] [green]\"$uni\"[/] "
                "[bold cyan]--extra-images[/] "
                "[green]\"${uni%_UNIT1.nii.gz}\"_inv-*_MP2RAGE.nii.gz[/]\n"
                "[bold white]done[/]",
            ),
            Text.from_markup(f"\n[dim]{CITATION_NOTICE}[/]"),
        )
        formatter.write(Padding(content, formatter.config.padding_epilog))


def _extra_images_or_batch() -> Padding:
    """Draw --extra-images and --batch side by side, so the difference is plain."""
    table = Table(
        title=Text.from_markup("[bold yellow]--extra-images or --batch?[/]"),
        title_justify="left",
        box=box.ROUNDED,
        border_style="yellow",
        show_lines=True,
        expand=True,
    )
    table.add_column("", style="bold", no_wrap=True)
    table.add_column(f"[bold {_ONE_SCAN}]A: -i with --extra-images[/]", ratio=1)
    table.add_column(f"[bold {_BATCH}]B: --batch[/]", ratio=1)
    for row in (
        ("For", "Other images from the same session as -i: MP2RAGE INV1, INV2, and UNI, or "
         "GRE echoes (4D is fine)", "Separate scans, such as one T1w for each subject"),
        ("Registered", "Once, on the -i scan", "Once for every scan"),
        ("Deface mask", "The same mask for every image", "Each scan gets its own"),
        ("With --reface", "Only the -i scan is refaced", "Every scan is refaced"),
        ("If one fails", "The whole run stops", "The other scans still run"),
        ("Example",
         "[bold white]faceoff[/] [bold cyan]-i[/] [green]sub-01_UNIT1.nii.gz[/] "
         "[bold cyan]--extra-images[/] [green]sub-01_inv-*_MP2RAGE.nii.gz[/]",
         "[bold white]faceoff[/] [bold cyan]--batch[/] [green]sub-*_T1w.nii.gz[/]"),
    ):
        table.add_row(*(Text.from_markup(cell) for cell in row))
    return Padding(
        Group(table, Text.from_markup(
            "[dim]Both take file names separated by commas, spaces, or both. They cannot be "
            "used together.[/]"
        )),
        (1, 0, 0, 0),
    )


def _at_least_one(context: Any, parameter: Any, value: int | None) -> int | None:
    """Refuse a thread count below 1."""
    if value is not None and value < 1:
        raise click.BadParameter("must be 1 or more.")
    return value


def _split_names(items: list[str]) -> tuple[Path, ...]:
    """Turn file names given with commas, spaces, or both into a list of paths."""
    return tuple(Path(name.strip()) for item in items for name in item.split(",") if name.strip())


def _resolve_threads(threads: int | None) -> int:
    """Return how many threads ANTs may use: --threads if given, otherwise
    ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS if set, otherwise every core."""
    if threads is not None:
        return threads
    if env_threads := os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        return int(env_threads)
    return os.cpu_count() or 1


def _deface_with_timer(path: Path, options: deface.Options) -> None:
    """Deface one scan while a "time elapsed" line ticks below the log (in a terminal only)."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[dim]Time elapsed:[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
        disable=not console.is_terminal,
    ) as progress:
        progress.add_task("", total=None)
        deface.run(path, options, ConsoleReporter())


@click.command(
    name="faceoff",
    cls=FaceOffCommand,
    help=(
        "Deface anatomical MRI scans using ANTs in Docker, with optional reorientation to "
        "MNI152 template space and optional refacing."
    ),
    epilog=CITATION_NOTICE,
    no_args_is_help=True,
    # allow_extra_args collects the scans after the first one in `--batch a.nii.gz b.nii.gz`
    context_settings={"help_option_names": ["-h", "--help"], "allow_extra_args": True},
)
@click.option(
    "-i", "--input", "input_file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="The scan to deface (.nii or .nii.gz).",
)
@click.option(
    "--batch", metavar="FILES",
    help="Several separate scans (commas or spaces between names), each registered and "
    "defaced on its own. If ANTs fails on one, or a file is missing, the others still run.",
)
@click.option(
    "--extra-images", multiple=True, metavar="FILES",
    help="Other images from the same session as -i (commas or spaces between names), for "
    "example MP2RAGE INV1, INV2, and UNI, or GRE echoes (4D is fine). They reuse the -i scan's "
    "registration, so they get its deface mask and reorientation; they are not refaced.",
)
@click.option(
    "--reorient/--no-reorient", default=True, show_default=True,
    help="Also write the defaced scan and its deface mask in template orientation (only the "
    "header changes, nothing is resampled). The ITK and FSL transforms are saved either way.",
)
@click.option(
    "--crop/--no-crop", default=True, show_default=True,
    help=f"Trim the reoriented outputs to template slices {TEMPLATE_CROP_Z[0]} to "
    f"{TEMPLATE_CROP_Z[1] - 1} along z. Whole slices are dropped; nothing is resampled.",
)
@click.option(
    "--reface", is_flag=True,
    help="Also write a refaced scan, with the template's face in place of the removed one.",
)
@click.option(
    "-n", "--threads", type=int, default=None, metavar="N", callback=_at_least_one,
    help="How many CPU threads ANTs may use. Default: ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS if "
    "set, otherwise every core.",
)
@click.option(
    "--syn", is_flag=True,
    help="Not required; included for completeness. Adds a slower registration and uses it "
    "for the deface mask. The default registration already gives almost the same mask.",
)
@click.option("-d", "depad", is_flag=True, hidden=True, help="Deprecated; ignored.")
@click.version_option(package_version(), "--version", prog_name="faceoff")
@click.pass_context
def cli(
    context: click.Context,
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
    if extra_images and batch:
        raise click.UsageError("--extra-images belongs to one scan; use it with -i, not --batch.")
    # Names after --batch or --extra-images may be separated by spaces as well as commas; the
    # shell hands the space-separated ones over as extra arguments.
    if context.args and not (batch or extra_images):
        raise click.UsageError(
            f"Unexpected extra argument: {context.args[0]}. To deface several scans, use "
            "--batch; for other images of the same scan, use --extra-images."
        )
    extras = _split_names([*extra_images, *context.args]) if extra_images else ()
    files = _split_names([batch, *context.args]) if batch else (input_file,)
    if extras:  # catch a mistyped extra image before Docker or the template are fetched
        try:
            deface.check_inputs(input_file, deface.Options(threads=1, extra_images=extras))
        except (FileNotFoundError, ValueError) as problem:
            raise click.BadParameter(str(problem), param_hint="--extra-images") from problem

    print_banner()
    if depad:
        log("[yellow]-d (depadding) is deprecated and ignored.[/]")
    try:
        ensure_docker_image()
        ensure_template(log=log)
    except RuntimeError as failure:
        error(str(failure))
        raise SystemExit(1) from failure

    options = deface.Options(
        threads=_resolve_threads(threads), syn=syn, reorient=reorient, crop=crop, reface=reface,
        extra_images=extras,
    )
    if len(files) > 1:
        quote("This is turning into a real marriage.", "Face/Off (1997)")
        console.print()

    failed = []
    for path in files:
        try:
            _deface_with_timer(path, options)
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
    """Start the command line (used by `python -m faceoff`)."""
    cli()
