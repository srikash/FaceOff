"""Deface one scan from start to finish: register, remove the face, reface if asked, and
reorient."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib

from . import masking
from .ants import AntsRunner, Container
from .registration import Stage, register
from .reorient import Crop, TalReorientation
from .scratch import workspace
from .template import Template


@dataclass(frozen=True)
class Options:
    """The choices for one run. The defaults are the same as the command line's."""

    threads: int
    # Not required: the affine alone already gives the deface mask. Kept for completeness.
    syn: bool = False
    # Also write the outputs in template orientation (header change only).
    reorient: bool = True
    # Trim those template-orientation outputs to template slices TEMPLATE_CROP_Z. Does nothing
    # without reorient.
    crop: bool = True
    # Also write a copy with the template's face put in place of the removed one.
    reface: bool = False
    # Other images from the same session and scanner space as the input (other MP2RAGE
    # images, GRE echoes, ...): they get the same deface mask and reorientation, not a face.
    extra_images: tuple[Path, ...] = ()
    # The template to register to; the tests pass a small synthetic one.
    template: Template = field(default_factory=Template.default)
    # How ANTs is run: Docker by default, or Apptainer/Singularity.
    container: Container = field(default_factory=Container)


@dataclass(frozen=True)
class Outputs:
    """The files a run writes. A field that is empty means that file is not written with
    these options.

    Files for the input are written next to the input, and files for each extra image next
    to that image. `tal_` files are in template orientation.
    """

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

    @classmethod
    def for_input(cls, scan: Path, extras: list[Path], options: Options) -> Outputs:
        """Work out every output file name for this scan, its extra images, and options."""
        name = strip_extension(scan)
        extra_names = [strip_extension(extra) for extra in extras]
        tal = options.reorient
        return cls(
            deface_mask=Path(f"{name}_defaceMask.nii.gz"),
            defaced=Path(f"{name}_defaced.nii.gz"),
            txn_itk=Path(f"{name}_txn-to-tal_itk.tfm"),
            txn_fsl=Path(f"{name}_txn-to-tal_fsl.mat"),
            refaced=Path(f"{name}_refaced.nii.gz") if options.reface else None,
            tal_defaced=Path(f"{name}_tal_defaced.nii.gz") if tal else None,
            tal_deface_mask=Path(f"{name}_tal_defaceMask.nii.gz") if tal else None,
            tal_refaced=Path(f"{name}_tal_refaced.nii.gz") if tal and options.reface else None,
            extra_defaced=tuple(Path(f"{n}_defaced.nii.gz") for n in extra_names),
            extra_tal_defaced=(
                tuple(Path(f"{n}_tal_defaced.nii.gz") for n in extra_names) if tal else ()
            ),
        )

    def tal_pairs(self) -> list[tuple[Path, Path]]:
        """Return (image, its template-orientation copy) for every tal_ file to write; the
        input's defaced image comes first."""
        pairs = [
            (self.defaced, self.tal_defaced),
            (self.deface_mask, self.tal_deface_mask),
            (self.refaced, self.tal_refaced),
            *zip(self.extra_defaced, self.extra_tal_defaced),
        ]
        return [(source, target) for source, target in pairs if source and target]

    def written(self) -> list[Path]:
        """Return every file this run writes."""
        paths: list[Path] = []
        for value in vars(self).values():
            if isinstance(value, Path):
                paths.append(value)
            elif isinstance(value, tuple):
                paths.extend(value)
        return paths


class Reporter:
    """Where a run reports its progress. This one stays silent; the command line uses
    `messages.ConsoleReporter`, which prints to the terminal.

    A run calls `begin` once, `step` after each finished step, `cropped` once if the
    template-orientation outputs are cropped, and `end` once.
    """

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None:
        """Called once, before anything is computed."""

    def step(self, message: str) -> None:
        """Called after each step finishes, with a short description of it."""

    def cropped(self, crop: Crop) -> None:
        """Called once with the slices of the input that were kept."""

    def end(self) -> None:
        """Called once, after the last output is written."""


def strip_extension(path: Path) -> Path:
    """Return the file name without .nii or .nii.gz (`scan.nii.gz` becomes `scan`).

    Raises ValueError for any other file type.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return path.parent / name[:-7]
    if name.endswith(".nii"):
        return path.parent / name[:-4]
    raise ValueError(f"Unsupported extension: {path.name}. Must be .nii or .nii.gz")


def check_inputs(input_file: Path, options: Options) -> tuple[Path, list[Path]]:
    """Check the input scan and any extra images before anything runs.

    Every file must exist and be a .nii or .nii.gz file, and the input must not also be
    listed as an extra image. Returns the full paths of the input and the extra images.
    Raises FileNotFoundError or ValueError if something is wrong.
    """
    subject = input_file.resolve()
    if not subject.exists():
        raise FileNotFoundError(f"Input file not found: {subject}")
    strip_extension(subject)
    extras = [path.resolve() for path in options.extra_images]
    for extra in extras:
        if not extra.exists():
            raise FileNotFoundError(f"Extra image not found: {extra}")
        strip_extension(extra)
        if extra == subject:
            raise ValueError(f"{extra.name} is the input itself; do not list it in extra images.")
    return subject, extras


def run(
    input_file: Path,
    options: Options,
    reporter: Reporter | None = None,
    ants: AntsRunner | None = None,
) -> Outputs:
    """Deface one scan and write the outputs next to it.

    ANTs runs as `options.container` says (Docker by default), unless another way of running
    it is passed as `ants` (the tests do this). Returns the names of the files written.
    """
    template = options.template
    subject, extras = check_inputs(input_file, options)
    reporter = reporter or Reporter()
    outputs = Outputs.for_input(subject, extras, options)
    reporter.begin(subject, options, outputs)

    with workspace() as ws:
        ants = ants or options.container.runner(options.threads, scratch=ws.root)

        tx = register(ants, ws, subject, template, syn=options.syn, reface=options.reface)
        reporter.step("registration to the template")

        # The template mask marks the region to remove; the deface mask is its inverse.
        warped_face = ws.path("face_mask_in_subject.nii.gz")
        tx.to_subject(template.face_mask, warped_face, Stage.DEFACE)
        keep = masking.keep_mask(nib.load(warped_face))
        nib.save(keep, outputs.deface_mask)
        reporter.step("deface mask")

        defaced = masking.deface(nib.load(subject), keep)
        nib.save(defaced, outputs.defaced)
        reporter.step("face taken… off")

        # Extra images may have their own voxel grid, so the face mask is warped onto each
        # one's grid rather than reused; on the input's grid this gives the same mask.
        for n, (extra, target) in enumerate(zip(extras, outputs.extra_defaced, strict=True)):
            warped = ws.path(f"face_mask_in_extra{n}.nii.gz")
            tx.to_subject(template.face_mask, warped, Stage.DEFACE, reference=extra)
            nib.save(masking.deface(nib.load(extra), masking.keep_mask(nib.load(warped))), target)
        if extras:
            reporter.step(f"face taken… off {len(extras)} extra image(s)")

        refaced = None
        if options.reface:
            ref_in_subject = ws.path("template_ref_in_subject.nii.gz")
            brain_in_subject = ws.path("template_brain_in_subject.nii.gz")
            tx.to_subject(template.t1w, ref_in_subject, Stage.REFACE, "Linear")
            tx.to_subject(template.brain_mask, brain_in_subject, Stage.REFACE)
            refaced, scale = masking.reface(
                defaced, keep, nib.load(ref_in_subject), nib.load(brain_in_subject)
            )
            nib.save(refaced, outputs.refaced)
            reporter.step(f"template face inserted (intensity scale {scale:.3g})")

        # The face is already removed. Save the rotation part of the affine; unless switched
        # off, write the images in template orientation (header only, no resampling).
        tal = TalReorientation.from_ants_affine(ants, ws, tx.affine, template)
        tal.write_transforms(subject, outputs.txn_itk, outputs.txn_fsl)
        if options.reorient:
            input_crop = tal.write_images(outputs.tal_pairs(), options.crop)[0]
            if input_crop is not None:
                reporter.cropped(input_crop)
            reporter.step("reorientation (header only) and ITK/FSL transforms")
        else:
            reporter.step("ITK/FSL transforms (image not reoriented)")

    reporter.end()
    return outputs
