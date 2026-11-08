"""The container files must stay in step with the code."""

from pathlib import Path

from faceoff.ants import ANTS_IMAGE

ROOT = Path(__file__).resolve().parent.parent


def test_the_dockerfile_takes_ants_from_the_image_faceoff_expects():
    assert f"ARG ANTS_IMAGE={ANTS_IMAGE}\n" in (ROOT / "Dockerfile").read_text()


def test_the_docker_build_context_is_an_allowlist_that_keeps_scans_out():
    lines = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*"  # everything is excluded unless allowed below
    allowed = {line[1:] for line in lines if line.startswith("!")}
    assert "testdata" not in allowed and "tempData" not in allowed
    assert {"pyproject.toml", "uv.lock", "faceoff", "licences"} <= allowed
