"""A small Rich console wrapper: timestamped log lines, success() and error()."""

from __future__ import annotations

from datetime import UTC, datetime

from rich.console import Console

console = Console()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    """Print a timestamped progress line. soft_wrap keeps file paths on one line."""
    console.print(f"[dim]{_now()}[/] {message}", soft_wrap=True)


def warning(message: str) -> None:
    """Print a timestamped warning."""
    console.print(f"[dim]{_now()}[/] [yellow]Warning:[/] {message}", soft_wrap=True)


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
    """A short duration: "6.4s" under a minute, otherwise "3m 15s"."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(int(seconds), 60)
    return f"{minutes}m {remaining}s"
