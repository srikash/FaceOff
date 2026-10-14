import hashlib
from pathlib import Path

import pytest

from faceoff import template, template_files


@pytest.fixture
def fake_files(monkeypatch):
    payloads = {name: f"content of {name}".encode() for name in template_files.TEMPLATE_FILES}
    monkeypatch.setattr(
        template_files, "TEMPLATE_FILES",
        {name: hashlib.md5(data).hexdigest() for name, data in payloads.items()},
    )
    return payloads


def _downloader(payloads, calls):
    def download(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_bytes(payloads[url.split("/files/")[1].split("/content")[0]])
    return download


def test_downloads_missing_files_then_skips(tmp_path, fake_files):
    calls: list[str] = []
    template_files.fetch_missing(tmp_path, _downloader(fake_files, calls))
    assert len(calls) == len(fake_files)
    assert all("zenodo.org/api/records/23328835/files/" in url for url in calls)
    template_files.fetch_missing(tmp_path, _downloader(fake_files, calls))
    assert len(calls) == len(fake_files)  # nothing re-downloaded


def test_corrupt_file_is_redownloaded(tmp_path, fake_files):
    calls: list[str] = []
    template_files.fetch_missing(tmp_path, _downloader(fake_files, calls))
    victim = tmp_path / next(iter(fake_files))
    victim.write_bytes(b"truncated")
    template_files.fetch_missing(tmp_path, _downloader(fake_files, calls))
    assert len(calls) == len(fake_files) + 1
    assert victim.read_bytes() == fake_files[victim.name]


def test_checksum_mismatch_is_an_error_and_leaves_no_file(tmp_path, fake_files):
    def bad_download(url: str, dest: Path) -> None:
        dest.write_bytes(b"not the template")

    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        template_files.fetch_missing(tmp_path, bad_download)
    assert list(tmp_path.iterdir()) == []


def test_network_failure_is_a_runtime_error(tmp_path, fake_files):
    def offline(url: str, dest: Path) -> None:
        raise OSError("offline")

    with pytest.raises(RuntimeError, match="Could not download"):
        template_files.fetch_missing(tmp_path, offline)


def test_bundled_files_are_used_only_when_complete(tmp_path, monkeypatch, fake_files):
    monkeypatch.setattr(template, "_BUNDLED_DIR", tmp_path / "data")
    cache = str(tmp_path / "cache")
    template._default_template.cache_clear()
    found = template._default_template(None, cache)
    assert found.folder == tmp_path / "cache" / "faceoff" / "zenodo-23328835"

    (tmp_path / "data").mkdir()
    for name, data in fake_files.items():
        (tmp_path / "data" / name).write_bytes(data)
    template._default_template.cache_clear()
    assert template._default_template(None, cache).folder == tmp_path / "data"
    template._default_template.cache_clear()


def test_environment_variable_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("FACEOFF_TEMPLATE_DIR", str(tmp_path / "mine"))
    assert template.Template.default().folder == tmp_path / "mine"
