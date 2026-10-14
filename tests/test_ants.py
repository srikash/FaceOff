from pathlib import Path

import pytest

from faceoff import ants as ants_module
import sys

from faceoff.ants import (
    REQUIRED_TOOLS,
    AntsError,
    ApptainerAnts,
    Container,
    DockerAnts,
    LocalAnts,
)

# conftest.py replaces `local_ants_available` in every test; keep the real one for its own test.
REAL_LOCAL_ANTS_AVAILABLE = ants_module.local_ants_available


def _mounts(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, part in enumerate(cmd) if part == "--mount"]


def test_docker_command_sets_threads_image_and_tool():
    ants = DockerAnts(threads=7, scratch=Path("/tmp/2026-10-13T00:36:41_abc"), image="antsx/ants:test")
    cmd = ants.command("antsApplyTransforms", ["--version"])
    assert cmd[:3] == ["docker", "run", "--rm"] and "--init" in cmd
    assert "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=7" in cmd
    assert cmd[-3:] == ["antsx/ants:test", "antsApplyTransforms", "--version"]


def test_mounts_come_from_the_arguments(tmp_path):
    scratch = tmp_path / "2026-10-13T00:36:41_abc"
    (tmp_path / "template").mkdir()
    (tmp_path / "data").mkdir()
    ants = DockerAnts(threads=1, scratch=scratch)
    cmd = ants.command("antsRegistration", [
        "--metric", f"MI[{tmp_path}/template/ref.nii.gz,{tmp_path}/data/sub.nii.gz,1,32]",
        "--output", f"{scratch}/affine_",
        "--initial-moving-transform", scratch / "init.mat",
    ])
    assert _mounts(cmd) == [
        f"type=bind,source={scratch},target={scratch}",  # scratch: the only writable mount
        f"type=bind,source={tmp_path}/data,target={tmp_path}/data,readonly",
        f"type=bind,source={tmp_path}/template,target={tmp_path}/template,readonly",
    ]


def test_nested_folders_are_mounted_once(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    ants = DockerAnts(threads=1, scratch=tmp_path / "s")
    cmd = ants.command("x", [f"{tmp_path}/a/f.nii.gz", f"{tmp_path}/a/b/g.nii.gz"])
    assert _mounts(cmd)[1:] == [f"type=bind,source={tmp_path}/a,target={tmp_path}/a,readonly"]


def test_apptainer_command_keeps_the_host_out(tmp_path):
    scratch = tmp_path / "2026-10-13T00:36:41_abc"
    (tmp_path / "data").mkdir()
    ants = ApptainerAnts(threads=3, scratch=scratch, image=Path("/c/ants.sif"),
                         executable="/usr/bin/apptainer")
    cmd = ants.command("antsApplyTransforms", ["--input", f"{tmp_path}/data/sub.nii.gz"])
    assert cmd[:3] == ["/usr/bin/apptainer", "exec", "--containall"]
    assert cmd[cmd.index("--env") + 1] == "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=3"
    assert _mounts(cmd) == [
        f"type=bind,source={scratch},destination={scratch}",  # the only writable mount
        f"type=bind,source={tmp_path}/data,destination={tmp_path}/data,ro",
    ]
    assert cmd[-4:-2] == ["/c/ants.sif", "antsApplyTransforms"]


def test_singularity_is_used_when_apptainer_is_missing(monkeypatch):
    found = {"singularity": "/opt/bin/singularity"}
    monkeypatch.setattr(ants_module.shutil, "which", found.get)
    assert ants_module._apptainer_executable() == "/opt/bin/singularity"
    monkeypatch.setattr(ants_module.shutil, "which", {}.get)
    with pytest.raises(RuntimeError, match="Neither apptainer nor singularity"):
        ants_module._apptainer_executable()


def test_apptainer_image_is_kept_in_the_cache_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert Container("apptainer").image == str(tmp_path / "faceoff" / "ants-2.6.5.sif")
    assert Container().image == "antsx/ants:2.6.5"


def test_image_file_needs_apptainer():
    with pytest.raises(ValueError, match="--engine apptainer"):
        Container("docker", Path("ants.sif"))
    with pytest.raises(ValueError, match="Unknown engine"):
        Container("podman")


def test_local_command_is_just_the_tool_and_its_arguments():
    assert LocalAnts(threads=2).command("antsRegistration", ["--version", Path("/a/b")]) == [
        "antsRegistration", "--version", "/a/b",
    ]


def test_local_run_sets_the_thread_count_and_reports_failure(tmp_path):
    out = tmp_path / "threads.txt"
    code = f"import os; open({str(out)!r}, 'w').write(os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'])"
    LocalAnts(threads=5).run(sys.executable, ["-c", code])
    assert out.read_text() == "5"
    with pytest.raises(AntsError, match="exit code 3"):
        LocalAnts(threads=1).run(sys.executable, ["-c", "raise SystemExit(3)"])


def test_local_ants_is_available_only_when_every_tool_is_on_the_path(monkeypatch):
    monkeypatch.setattr(ants_module, "local_ants_available", REAL_LOCAL_ANTS_AVAILABLE)
    monkeypatch.setattr(ants_module.shutil, "which", lambda name: f"/opt/ants/bin/{name}")
    assert ants_module.local_ants_available()
    monkeypatch.setattr(
        ants_module.shutil, "which", lambda name: None if name == "antsAI" else "/x/" + name
    )
    assert not ants_module.local_ants_available()


def test_local_prepare_names_the_missing_tools(monkeypatch):
    monkeypatch.setattr(
        ants_module.shutil, "which", lambda name: None if name == "antsAI" else "/x/" + name
    )
    with pytest.raises(RuntimeError, match="antsAI"):
        Container("local").prepare()


def test_local_prepare_logs_the_version_and_warns_when_it_differs(monkeypatch):
    monkeypatch.setattr(ants_module.shutil, "which", lambda name: "/opt/ants/bin/" + name)
    for output, expected in [
        ("ANTs Version: 2.6.5.dev1-gabc\n", "Using ANTs 2.6.5.dev1-gabc"),
        ("ANTs Version: 2.4.3\n", "tested with 2.6.5"),
        ("no version here", "Could not read"),
    ]:
        monkeypatch.setattr(
            ants_module.subprocess, "run",
            lambda cmd, **kw: type("R", (), {"stdout": output})(),
        )
        messages: list[str] = []
        Container("local").prepare(messages.append)
        assert expected in messages[0]


def test_local_container_builds_a_local_runner():
    assert isinstance(Container("local").runner(threads=2, scratch=Path("/s")), LocalAnts)
    assert set(REQUIRED_TOOLS) == {"antsAI", "antsRegistration", "antsApplyTransforms", "ConvertTransformFile"}


def test_default_container_is_local_when_the_tools_exist_otherwise_docker(monkeypatch):
    monkeypatch.setattr(ants_module, "local_ants_available", lambda: True)
    assert Container.default() == Container("local")
    monkeypatch.setattr(ants_module, "local_ants_available", lambda: False)
    assert Container.default() == Container("docker")
    assert Container() == Container("docker")  # a bare Container() is always Docker
