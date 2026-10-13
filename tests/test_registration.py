from pathlib import Path

import pytest

from faceoff.ants import RecordingAnts
from faceoff.registration import Stage, register
from faceoff.workspace import Workspace

WS = Path("/WS")
SUBJECT = Path("/data/sub.nii.gz")


def _chain(syn: bool, reface: bool, stage: Stage) -> list[str]:
    """The transform arguments of the antsApplyTransforms call `to_subject` makes."""
    ants = RecordingAnts()
    tx = register(ants, Workspace(WS), SUBJECT, syn=syn, reface=reface)
    tx.to_subject(Path("/template/mask.nii.gz"), WS / "out.nii.gz", stage)
    tool, args = ants.calls[-1]
    assert tool == "antsApplyTransforms"
    assert args[args.index("--reference-image") + 1] == str(SUBJECT)
    return args[args.index("--verbose") + 2:]


def test_deface_affine_only_uses_inverse_affine():
    assert _chain(False, False, Stage.DEFACE) == ["--transform", "[/WS/affine_0GenericAffine.mat,1]"]


def test_deface_with_syn_uses_inverse_composite():
    assert _chain(True, False, Stage.DEFACE) == ["--transform", "/WS/syn_InverseComposite.h5"]


def test_reface_inverse_affine_comes_before_inverse_warp():
    """antsApplyTransforms: earlier transforms' inverses first, last-fitted warp last."""
    assert _chain(False, True, Stage.REFACE) == [
        "--transform", "[/WS/affine_0GenericAffine.mat,1]",
        "--transform", "/WS/face_1InverseWarp.nii.gz",
    ]


def test_reface_after_syn_is_second_warp():
    assert _chain(True, True, Stage.REFACE) == [
        "--transform", "/WS/syn_InverseComposite.h5",
        "--transform", "/WS/face_2InverseWarp.nii.gz",
    ]


def test_reface_without_reface_registration_is_an_error():
    with pytest.raises(ValueError):
        _chain(False, False, Stage.REFACE)


@pytest.mark.parametrize(
    ("syn", "reface", "n_registrations"), [(False, False, 1), (True, False, 2), (True, True, 3)]
)
def test_register_runs_requested_stages(syn, reface, n_registrations):
    ants = RecordingAnts()
    register(ants, Workspace(WS), SUBJECT, syn=syn, reface=reface)
    tools = [tool for tool, _ in ants.calls]
    assert tools[0] == "antsAI"
    assert tools.count("antsRegistration") == n_registrations


def test_reface_syn_starts_from_syn_composite():
    ants = RecordingAnts()
    register(ants, Workspace(WS), SUBJECT, syn=True, reface=True)
    reface_args = ants.calls[-1][1]
    start = reface_args[reface_args.index("--initial-moving-transform") + 1]
    assert start == "/WS/syn_Composite.h5"
