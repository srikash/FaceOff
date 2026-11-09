"""The version is written in several files; a release with one of them stale is a mistake."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_citation_file_has_the_package_version():
    assert f"version: {VERSION}\n" in (ROOT / "CITATION.cff").read_text()


def test_readme_badge_has_the_package_version():
    first_line = (ROOT / "README.md").read_text().splitlines()[0]
    assert f"version-{VERSION}-" in first_line and f"/tag/v{VERSION})" in first_line


def test_citation_page_has_the_package_version_everywhere():
    text = (ROOT / "docs" / "citation.md").read_text()
    assert f"(version {VERSION};" in text  # the methods sentence
    assert f"(Version {VERSION})" in text  # the reference
    assert f"version   = {{{VERSION}}}" in text  # the BibTeX entry
