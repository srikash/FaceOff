from pathlib import Path

import pytest
from click.testing import CliRunner

from faceoff import cli as cli_module
from faceoff.ants import AntsError


@pytest.fixture
def runs(monkeypatch):
    """Replace Docker, the template download and the pipeline; record each run."""
    calls = []

    def fake_run(path, options, reporter):
        calls.append((Path(path).name, options))
        if Path(path).name.startswith("bad"):
            raise AntsError("antsRegistration failed (exit code 1).")

    monkeypatch.setattr(cli_module, "ensure_docker_image", lambda: None)
    monkeypatch.setattr(cli_module, "ensure_template", lambda log: None)
    monkeypatch.setattr(cli_module.pipeline, "run", fake_run)
    return calls


def _scan(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"")
    return str(path)


def test_input_and_batch_are_exclusive(tmp_path, runs):
    result = CliRunner().invoke(
        cli_module.cli, ["-i", _scan(tmp_path, "a.nii.gz"), "--batch", "b.nii.gz"]
    )
    assert result.exit_code == 2
    assert "exactly one of" in result.output
    assert runs == []


def test_flags_reach_the_pipeline(tmp_path, runs):
    result = CliRunner().invoke(
        cli_module.cli,
        ["-i", _scan(tmp_path, "a.nii.gz"), "--reface", "--no-crop", "-n", "3"],
    )
    assert result.exit_code == 0, result.output
    [(name, options)] = runs
    assert name == "a.nii.gz"
    assert (options.threads, options.reface, options.crop, options.reorient, options.syn) == (
        3, True, False, True, False,
    )


def test_batch_continues_after_a_failure_and_exits_1(tmp_path, runs):
    batch = ",".join([_scan(tmp_path, "bad.nii.gz"), _scan(tmp_path, "good.nii.gz")])
    result = CliRunner().invoke(cli_module.cli, ["--batch", batch])
    assert result.exit_code == 1
    assert [name for name, _ in runs] == ["bad.nii.gz", "good.nii.gz"]
    assert "1 of 2 scans failed" in result.output


def test_version():
    result = CliRunner().invoke(cli_module.cli, ["--version"])
    assert result.exit_code == 0
    assert "faceoff" in result.output


def test_extra_images_are_split_on_commas(tmp_path, runs):
    a, b = _scan(tmp_path, "inv1.nii.gz"), _scan(tmp_path, "inv2.nii.gz")
    result = CliRunner().invoke(
        cli_module.cli, ["-i", _scan(tmp_path, "uni.nii.gz"), "--extra-images", f"{a},{b}"]
    )
    assert result.exit_code == 0, result.output
    assert runs[0][1].extra_images == (Path(a), Path(b))


def test_extra_images_not_with_batch(tmp_path, runs):
    result = CliRunner().invoke(
        cli_module.cli,
        ["--batch", _scan(tmp_path, "a.nii.gz"), "--extra-images", _scan(tmp_path, "b.nii.gz")],
    )
    assert result.exit_code == 2
    assert runs == []
