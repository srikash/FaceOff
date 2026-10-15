from pathlib import Path

import pytest

from faceoff.ants import RecordingAnts
from faceoff.registration import Stage, register
from faceoff.scratch import Workspace
from faceoff.template import Template

WS = Path("/WS")
SUBJECT = Path("/data/sub.nii.gz")
TEMPLATE = Template(Path("/template"))


def _register(ants, syn: bool, reface: bool):
    return register(ants, Workspace(WS), SUBJECT, TEMPLATE, syn=syn, reface=reface)


def _chain(syn: bool, reface: bool, stage: Stage) -> list[str]:
    """The transform arguments of the antsApplyTransforms call `to_subject` makes."""
    ants = RecordingAnts()
    tx = _register(ants, syn, reface)
    tx.to_subject(TEMPLATE.face_mask, WS / "out.nii.gz", stage)
    tool, args = ants.calls[-1]
    assert tool == "antsApplyTransforms"
    assert args[args.index("--reference-image") + 1] == str(SUBJECT)
    return args[args.index("--verbose") + 2:]


def test_deface_affine_only_uses_inverse_affine():
    assert _chain(False, False, Stage.DEFACE) == ["--transform", "[/WS/affine_0GenericAffine.mat,1]"]


def test_deface_with_syn_chains_affine_head_and_brain_warps():
    assert _chain(True, False, Stage.DEFACE) == [
        "--transform", "[/WS/affine_0GenericAffine.mat,1]",
        "--transform", "/WS/head_1InverseWarp.nii.gz",
        "--transform", "/WS/brain_2InverseWarp.nii.gz",
    ]


def test_reface_inverse_affine_comes_before_inverse_warp():
    """antsApplyTransforms: earlier transforms' inverses first, last-fitted warp last."""
    assert _chain(False, True, Stage.REFACE) == [
        "--transform", "[/WS/affine_0GenericAffine.mat,1]",
        "--transform", "/WS/face_1InverseWarp.nii.gz",
    ]


def test_reface_after_syn_is_third_warp():
    assert _chain(True, True, Stage.REFACE) == [
        "--transform", "[/WS/affine_0GenericAffine.mat,1]",
        "--transform", "/WS/head_1InverseWarp.nii.gz",
        "--transform", "/WS/brain_2InverseWarp.nii.gz",
        "--transform", "/WS/face_3InverseWarp.nii.gz",
    ]


def test_reface_without_reface_registration_is_an_error():
    with pytest.raises(ValueError):
        _chain(False, False, Stage.REFACE)


@pytest.mark.parametrize(
    ("syn", "reface", "n_registrations"), [(False, False, 1), (True, False, 3), (True, True, 4)]
)
def test_register_runs_requested_stages(syn, reface, n_registrations):
    ants = RecordingAnts()
    _register(ants, syn, reface)
    tools = [tool for tool, _ in ants.calls]
    assert tools[0] == "antsAI"
    assert tools.count("antsRegistration") == n_registrations


def test_each_syn_step_starts_from_the_transforms_fitted_before_it():
    """ANTs order: the last-applied transform first, the affine last."""
    ants = RecordingAnts()
    _register(ants, True, True)
    starts = [[str(a) for i, a in enumerate(args) if args[i - 1] == "--initial-moving-transform"]
              for tool, args in ants.calls if tool == "antsRegistration"][1:]
    assert starts == [
        ["/WS/affine_0GenericAffine.mat"],
        ["/WS/head_1Warp.nii.gz", "/WS/affine_0GenericAffine.mat"],
        ["/WS/brain_2Warp.nii.gz", "/WS/head_1Warp.nii.gz", "/WS/affine_0GenericAffine.mat"],
    ]


def test_registration_uses_the_given_template():
    ants = RecordingAnts()
    _register(ants, False, False)
    args = " ".join(ants.calls[1][1])
    assert f"MI[{TEMPLATE.t1w}," in args and f"[{TEMPLATE.brain_mask},1]" in args


def _after(args: list[str], flag: str) -> str | None:
    """The value that follows `flag` in an argument list, or None if the flag is absent."""
    return args[args.index(flag) + 1] if flag in args else None


def _syn_calls(syn: bool, reface: bool) -> list[tuple[str | None, ...]]:
    """(starting transform, mask, metric, shrink factors) of each SyN call, in order."""
    ants = RecordingAnts()
    _register(ants, syn, reface)
    calls = [args for tool, args in ants.calls if tool == "antsRegistration"][1:]
    flags = ("--initial-moving-transform", "--masks", "--metric", "--shrink-factors")
    return [tuple(_after(args, flag) for flag in flags) for args in calls]


MI = f"MI[{TEMPLATE.t1w},{SUBJECT},1,32]"
CC = f"CC[{TEMPLATE.t1w},{SUBJECT},1,2]"


def test_syn_fits_the_whole_head_with_mi_then_the_brain_with_cc():
    assert _syn_calls(True, False) == [
        ("/WS/affine_0GenericAffine.mat", None, MI, "10x6x4x2"),
        ("/WS/head_1Warp.nii.gz", f"[{TEMPLATE.brain_mask},1]", CC, "2x1"),
    ]


@pytest.mark.parametrize(("syn", "start"), [
    (False, "/WS/affine_0GenericAffine.mat"), (True, "/WS/brain_2Warp.nii.gz"),
])
def test_reface_fits_the_face_with_dense_mi(syn, start):
    assert _syn_calls(syn, True)[-1] == (start, f"[{TEMPLATE.reface_mask},1]", MI, "10x6x4x2")


def test_no_syn_step_samples_the_metric():
    ants = RecordingAnts()
    _register(ants, True, True)
    syn_metrics = [_after(args, "--metric") for _, args in ants.calls[2:]]
    assert len(syn_metrics) == 3 and not any("Regular" in m for m in syn_metrics)
