"""The FaceOff pipeline for one image: register, deface, optionally reface, reorient."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import nibabel as nib
import numpy as np

from . import faceedit
from .ants import AntsRunner, DockerAnts
from .registration import Stage, register
from .reorient import Crop, TalReorientation
from .template import TEMPLATE_BRAIN_MASK, TEMPLATE_FACE_MASK, TEMPLATE_REF
from .workspace import workspace


@dataclass(frozen=True)
class Options:
    threads: int
    # Not required: the affine alone already gives the deface mask. Kept for completeness.
    syn: bool = False
    reorient: bool = True
    crop: bool = True
    reface: bool = False
    # Images in the same scanner space as the input (other MP2RAGE images, GRE echoes, ...):
    # they get the same deface mask and reorientation. Not refaced.
    extra_images: tuple[Path, ...] = ()


@dataclass(frozen=True)
class Outputs:
    deface_mask: Path
    defaced: Path
    txn_itk: Path
    txn_fsl: Path
    refaced: Path | None = None
    tal_defaced: Path | None = None
    tal_deface_mask: Path | None = None
    tal_refaced: Path | None = None
    extra_defaced: tuple[Path, ...] = ()
    extra_tal_defaced: tuple[Path, ...] = ()

    def written(self) -> list[Path]:
        """Every output file, in the order they are written."""
        paths: list[Path] = []
        for value in vars(self).values():
            if isinstance(value, Path):
                paths.append(value)
            elif isinstance(value, tuple):
                paths.extend(value)
        return paths


class Reporter(Protocol):
    """Progress sink. `ConsoleReporter` prints; `SilentReporter` does nothing."""

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None: ...
    def registering(self, syn: bool, reface: bool) -> None: ...
    def step(self, message: str) -> None: ...
    def cropped(self, crop: Crop) -> None: ...
    def end(self) -> None: ...


class SilentReporter:
    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None: ...
    def registering(self, syn: bool, reface: bool) -> None: ...
    def step(self, message: str) -> None: ...
    def cropped(self, crop: Crop) -> None: ...
    def end(self) -> None: ...


def strip_extension(path: Path) -> Path:
    name = path.name
    if name.endswith(".nii.gz"):
        return path.parent / name[:-7]
    if name.endswith(".nii"):
        return path.parent / name[:-4]
    raise ValueError(f"Unsupported extension: {path.name}. Must be .nii or .nii.gz")


def run(
    input_file: Path,
    options: Options,
    reporter: Reporter | None = None,
    ants: AntsRunner | None = None,
) -> Outputs:
    """Process one image; outputs are written next to it. ANTs runs in Docker unless `ants`
    is given."""
    subject = input_file.resolve()
    if not subject.exists():
        raise FileNotFoundError(f"Input file not found: {subject}")
    reporter = reporter or SilentReporter()
    prefix = strip_extension(subject)
    extras = [path.resolve() for path in options.extra_images]
    for extra in extras:
        if not extra.exists():
            raise FileNotFoundError(f"Extra image not found: {extra}")
        if extra == subject:
            raise ValueError(f"{extra.name} is the input itself; do not list it in extra images.")
    extra_prefixes = [strip_extension(extra) for extra in extras]
    outputs = Outputs(
        deface_mask=Path(f"{prefix}_defaceMask.nii.gz"),
        defaced=Path(f"{prefix}_defaced.nii.gz"),
        txn_itk=Path(f"{prefix}_txn-to-tal_itk.tfm"),
        txn_fsl=Path(f"{prefix}_txn-to-tal_fsl.mat"),
        refaced=Path(f"{prefix}_refaced.nii.gz") if options.reface else None,
        tal_defaced=Path(f"{prefix}_tal_defaced.nii.gz") if options.reorient else None,
        tal_deface_mask=Path(f"{prefix}_tal_defaceMask.nii.gz") if options.reorient else None,
        tal_refaced=(
            Path(f"{prefix}_tal_refaced.nii.gz") if options.reorient and options.reface else None
        ),
        extra_defaced=tuple(Path(f"{p}_defaced.nii.gz") for p in extra_prefixes),
        extra_tal_defaced=(
            tuple(Path(f"{p}_tal_defaced.nii.gz") for p in extra_prefixes)
            if options.reorient else ()
        ),
    )
    reporter.begin(subject, options, outputs)

    with workspace() as ws:
        ants = ants or DockerAnts(options.threads, scratch=ws.root)

        reporter.registering(options.syn, options.reface)
        tx = register(ants, ws, subject, syn=options.syn, reface=options.reface)
        reporter.step("registration to the template")

        # The template mask marks the region to remove; the deface mask is its inverse.
        warped_face = ws.path("face_mask_in_subject.nii.gz")
        tx.to_subject(TEMPLATE_FACE_MASK, warped_face, Stage.DEFACE)
        keep = faceedit.keep_mask(nib.load(warped_face))
        nib.save(keep, outputs.deface_mask)
        reporter.step("deface mask")

        defaced = faceedit.deface(nib.load(subject), keep)
        nib.save(defaced, outputs.defaced)
        reporter.step("face taken… off")

        # Extra images may have their own grid (or be 4D), so the face mask is warped onto each
        # one's grid rather than reused; on the input's grid this gives the same mask.
        for n, (extra, target) in enumerate(zip(extras, outputs.extra_defaced)):
            image = nib.load(extra)
            reference = extra
            if image.ndim > 3:
                reference = ws.path(f"extra{n}_grid.nii.gz")
                nib.save(nib.Nifti1Image(np.zeros(image.shape[:3], np.uint8), image.affine), reference)
            warped = ws.path(f"face_mask_in_extra{n}.nii.gz")
            tx.to_subject(TEMPLATE_FACE_MASK, warped, Stage.DEFACE, reference=reference)
            nib.save(faceedit.deface(image, faceedit.keep_mask(nib.load(warped))), target)
        if extras:
            reporter.step(f"face taken… off {len(extras)} extra image(s)")

        refaced = None
        if options.reface:
            ref_in_subject = ws.path("template_ref_in_subject.nii.gz")
            brain_in_subject = ws.path("template_brain_in_subject.nii.gz")
            tx.to_subject(TEMPLATE_REF, ref_in_subject, Stage.REFACE, "Linear")
            tx.to_subject(TEMPLATE_BRAIN_MASK, brain_in_subject, Stage.REFACE)
            refaced, scale = faceedit.reface(
                defaced, keep, nib.load(ref_in_subject), nib.load(brain_in_subject)
            )
            nib.save(refaced, outputs.refaced)
            reporter.step(f"template face inserted (intensity scale {scale:.3g})")

        # The face is already removed. Save the rotation component of the affine; unless
        # disabled, write the images in template orientation (header only, no resampling).
        tal = TalReorientation.from_ants_affine(ants, ws, tx.affine)
        tal.write_transforms(subject, outputs.txn_itk, outputs.txn_fsl)
        if options.reorient:
            pairs = [
                (outputs.defaced, outputs.tal_defaced),
                (outputs.deface_mask, outputs.tal_deface_mask),
                (outputs.refaced, outputs.tal_refaced),
                *zip(outputs.extra_defaced, outputs.extra_tal_defaced),
            ]
            for n, (source, target) in enumerate(pairs):
                if source is not None and target is not None:
                    cropped = tal.write_image(source, target, options.crop)
                    if n == 0 and cropped is not None:
                        reporter.cropped(cropped)
            reporter.step("reorientation (header only) and ITK/FSL transforms")
        else:
            reporter.step("ITK/FSL transforms (image not reoriented)")

    reporter.end()
    return outputs
