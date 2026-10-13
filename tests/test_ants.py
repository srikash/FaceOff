from pathlib import Path

from faceoff.ants import DockerAnts


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
