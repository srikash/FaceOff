"""Every combination of --reface, --enucleate, --renucleate, and --syn, against what should
happen to the face and the eyes."""

from itertools import product

import pytest

from faceoff.regions import Regions
from faceoff.registration import Stage

# (reface, enucleate, renucleate) -> (removes eyes, fills face, fills eyes)
EXPECTED = {
    (False, False, False): (False, False, False),
    (False, True, False): (True, False, False),
    (False, False, True): (True, False, True),
    (False, True, True): (True, False, True),
    (True, False, False): (False, True, False),
    (True, True, False): (True, True, True),  # --reface --enucleate puts the eyes back too
    (True, False, True): (True, True, True),
    (True, True, True): (True, True, True),
}


@pytest.mark.parametrize(("flags", "syn"), list(product(EXPECTED, (False, True))))
def test_every_flag_combination(flags, syn):
    regions = Regions(*flags, syn=syn)
    removes_eyes, fills_face, fills_eyes = EXPECTED[flags]
    assert (regions.removes_eyes, regions.fills_face, regions.fills_eyes) == EXPECTED[flags]
    assert regions.writes_refaced == (fills_face or fills_eyes)
    assert regions.needs_face_registration == (fills_face or removes_eyes)
    assert regions.face_mask_stage == (Stage.NONLINEAR_BRAIN if syn else Stage.AFFINE)
    assert regions.eye_mask_stage == Stage.NONLINEAR_FACE


def test_the_start_up_line_says_what_happens():
    assert Regions().describe() == (
        "Removes: face.  Fills from the template: nothing.  Registration: affine."
    )
    assert Regions(reface=True, enucleate=True, syn=True).describe() == (
        "Removes: face, eyes.  Fills from the template: face, eyes.  Registration: affine, "
        "then nonlinear brain (MI, then CC), then nonlinear face (MI)."
    )
