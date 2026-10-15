"""What happens to the face and the eyes, worked out once from the command-line flags.

Every other part of FaceOff (registration, masking, the output file names, the start-up
message, the QC page) asks `Regions` instead of combining --reface, --enucleate, --renucleate,
and --syn itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from .registration import Stage


@dataclass(frozen=True)
class Regions:
    """The face and eye choices for one run (the same names as the command-line flags)."""

    reface: bool = False  # put the template's face in place of the removed one
    enucleate: bool = False  # remove the eyes as well as the face
    renucleate: bool = False  # remove the eyes and put the template's eyes in their place
    syn: bool = False  # move the face mask with a nonlinear registration (--syn)

    @property
    def removes_eyes(self) -> bool:
        """True when the eyes are removed: --enucleate, or --renucleate, which implies it."""
        return self.enucleate or self.renucleate

    @property
    def fills_face(self) -> bool:
        """True when the removed face is filled with the template's face."""
        return self.reface

    @property
    def fills_eyes(self) -> bool:
        """True when the removed eyes are filled with the template's eyes: --renucleate, or
        --reface with --enucleate (which would otherwise leave half-filled eyeballs, because
        the face mask overlaps the eyes)."""
        return self.renucleate or (self.reface and self.enucleate)

    @property
    def writes_refaced(self) -> bool:
        """True when a refaced image is written: the face, the eyes, or both are filled."""
        return self.fills_face or self.fills_eyes

    @property
    def needs_face_registration(self) -> bool:
        """True when the nonlinear face registration is run: for the template face, and for
        anything to do with the eyes (they are removed and filled with that registration)."""
        return self.fills_face or self.removes_eyes

    @property
    def face_mask_stage(self) -> Stage:
        """The registration that moves the face mask onto the scan."""
        return Stage.NONLINEAR_BRAIN if self.syn else Stage.AFFINE

    @property
    def eye_mask_stage(self) -> Stage:
        """The registration that moves the eye mask onto the scan."""
        return Stage.NONLINEAR_FACE

    def describe(self) -> str:
        """One line saying what will happen, for the start-up message."""
        removed = "face, eyes" if self.removes_eyes else "face"
        filled = ", ".join(
            part for part, yes in (("face", self.fills_face), ("eyes", self.fills_eyes)) if yes
        )
        steps = ["affine"]
        if self.syn:
            steps.append("nonlinear brain (MI, then CC)")
        if self.needs_face_registration:
            steps.append("nonlinear face (MI)")
        return (
            f"Removes: {removed}.  Fills from the template: {filled or 'nothing'}.  "
            f"Registration: {', then '.join(steps)}."
        )
