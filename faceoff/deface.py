"""Deface one scan from start to finish: register, remove the face (and the eyes, if asked),
put the template's face and eyes back if asked, and reorient."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import nibabel as nib

from . import masking, qc
from .ants import Container
from .regions import Regions
from .registration import Stage, Transforms, register
from .reorient import Crop, TalReorientation
from .scratch import Workspace, workspace
from .template import Template


@dataclass(frozen=True)
class Options:
    """The choices for one run. The defaults are the same as the command line's."""

    threads: int
    # Not required: the affine alone already gives the deface mask. Kept for completeness.
    syn: bool = False
    # Also write the outputs in template orientation (header change only).
    reorient: bool = True
    # Trim those template-orientation outputs to the z range TEMPLATE_CROP_Z_MM. Does nothing
    # without reorient.
    crop: bool = True
    # Also write a copy with the template's face put in place of the removed one.
    reface: bool = False
    # Remove the eyes as well as the face (they are zeroed in the defaced images and the
    # deface mask).
    enucleate: bool = False
    # Also put the template's eyes in place of the removed ones (like reface, for the eyes).
    # This removes the eyes too, so it implies enucleate. With reface, the refaced image gets
    # both the face and the eyes; without it, the face stays removed there. Reface together
    # with enucleate already puts the eyes back, so renucleate is then redundant.
    renucleate: bool = False
    # Also write a QC page (name_faceoff_qc.html): a GIF of the defaced (and refaced) scan for
    # each image.
    qc: bool = True
    # Other images from the same session and scanner space as the input (other MP2RAGE
    # images, GRE echoes, ...): they get the same deface mask and reorientation, not a face.
    extra_images: tuple[Path, ...] = ()
    # The template to register to; the tests pass a small synthetic one.
    template: Template = field(default_factory=Template.default)
    # How ANTs is run: your own install if its tools are on your PATH, otherwise Docker (or
    # Apptainer/Singularity when chosen).
    container: Container = field(default_factory=Container.default)

    @property
    def regions(self) -> Regions:
        """What happens to the face and the eyes with these flags."""
        return Regions(self.reface, self.enucleate, self.renucleate, self.syn)


@dataclass(frozen=True)
class Outputs:
    """The files a run writes. A field that is empty means that file is not written with
    these options. The refaced files are written for reface, renucleate, or both.

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
    qc: Path | None = None
    extra_defaced: tuple[Path, ...] = ()
    extra_tal_defaced: tuple[Path, ...] = ()

    @classmethod
    def for_input(cls, scan: Path, extras: list[Path], options: Options) -> Outputs:
        """Work out every output file name for this scan, its extra images, and options."""
        name = strip_extension(scan)
        extra_names = [strip_extension(extra) for extra in extras]
        tal = options.reorient
        refaced = options.regions.writes_refaced
        return cls(
            deface_mask=Path(f"{name}_defaceMask.nii.gz"),
            defaced=Path(f"{name}_defaced.nii.gz"),
            txn_itk=Path(f"{name}_txn-to-tal_itk.tfm"),
            txn_fsl=Path(f"{name}_txn-to-tal_fsl.mat"),
            refaced=Path(f"{name}_refaced.nii.gz") if refaced else None,
            tal_defaced=Path(f"{name}_tal_defaced.nii.gz") if tal else None,
            tal_deface_mask=Path(f"{name}_tal_defaceMask.nii.gz") if tal else None,
            tal_refaced=Path(f"{name}_tal_refaced.nii.gz") if tal and refaced else None,
            qc=Path(f"{name}_faceoff_qc.html") if options.qc else None,
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

    A run calls `begin` once, `step` after each finished step, `warn` for a problem that does
    not stop the run, `cropped` once if the template-orientation outputs are cropped, and `end`
    once.
    """

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None:
        """Called once, before anything is computed."""

    def step(self, message: str) -> None:
        """Called after each step finishes, with a short description of it."""

    def warn(self, message: str) -> None:
        """Called when something optional, such as the QC page, could not be written."""

    def cropped(self, crop: Crop) -> None:
        """Called once with the slices of the input that were kept."""

    def end(self) -> None:
        """Called once, after the last output is written."""


def _warp_masks(
    tx: Transforms,
    ws: Workspace,
    template: Template,
    regions: Regions,
    label: str,
    reference: Path | None = None,
) -> tuple[nib.Nifti1Image, nib.Nifti1Image | None]:
    """Move the template's face mask, and its eye mask when the eyes are removed, onto the scan
    (or onto `reference`, an image in the same space with its own grid). The face mask goes
    with the affine (or the nonlinear brain registration with --syn); the eye mask with the
    nonlinear face registration.

    `label` names the files in the scratch folder. Returns the two masks, the second being
    None when the eyes stay.
    """
    face = ws.path(f"face_mask_in_{label}.nii.gz")
    tx.to_subject(template.face_mask, face, regions.face_mask_stage, reference=reference)
    if not regions.removes_eyes:
        return nib.load(face), None
    eyes = ws.path(f"eye_mask_in_{label}.nii.gz")
    tx.to_subject(template.eye_mask, eyes, regions.eye_mask_stage, reference=reference)
    return nib.load(face), nib.load(eyes)


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


def register_with_ants(ws: Workspace, subject: Path, options: Options) -> Transforms:
    """Register the scan to the template with ANTs, run as `options.container` says (your
    own install if it is on your PATH, otherwise Docker, by default)."""
    ants = options.container.runner(options.threads, scratch=ws.root)
    face = options.regions.needs_face_registration
    return register(ants, ws, subject, options.template, syn=options.syn, face=face)


def run(
    input_file: Path,
    options: Options,
    reporter: Reporter | None = None,
    registration: Callable[[Workspace, Path, Options], Transforms] = register_with_ants,
) -> Outputs:
    """Deface one scan and write the outputs next to it. Returns the names of the files
    written.

    `registration` registers the scan to the template: ANTs by default. The tests pass a
    stand-in that moves template images with a known affine.
    """
    template = options.template
    subject, extras = check_inputs(input_file, options)
    reporter = reporter or Reporter()
    outputs = Outputs.for_input(subject, extras, options)
    reporter.begin(subject, options, outputs)

    with workspace() as ws:
        regions = options.regions
        tx = registration(ws, subject, options)
        reporter.step("registration to the template")

        # The template masks mark the region to remove; the deface mask is its inverse.
        face, eyes = _warp_masks(tx, ws, template, regions, "subject")
        keep = masking.keep_mask(face, eyes)
        nib.save(keep, outputs.deface_mask)
        reporter.step("deface mask")

        defaced = masking.deface(nib.load(subject), keep)
        nib.save(defaced, outputs.defaced)
        reporter.step("face taken… off")

        # Extra images may have their own voxel grid, so the masks are warped onto each
        # one's grid rather than reused; on the input's grid this gives the same mask.
        qc_extras = []
        for n, (extra, target) in enumerate(zip(extras, outputs.extra_defaced, strict=True)):
            extra_face, extra_eyes = _warp_masks(tx, ws, template, regions, f"extra{n}", extra)
            extra_keep = masking.keep_mask(extra_face, extra_eyes)
            nib.save(masking.deface(nib.load(extra), extra_keep), target)
            if outputs.qc:  # the QC page reads the saved file back, one volume at a time
                qc_extras.append((extra.name, target))
        if extras:
            reporter.step(f"face taken… off {len(extras)} extra image(s)")

        refaced = fill = None
        if regions.writes_refaced:
            ref_in_subject = ws.path("template_ref_in_subject.nii.gz")
            brain_in_subject = ws.path("template_brain_in_subject.nii.gz")
            tx.to_subject(template.t1w, ref_in_subject, Stage.NONLINEAR_FACE, "Linear")
            tx.to_subject(template.brain_mask, brain_in_subject, Stage.NONLINEAR_FACE)
            fill = masking.fill_region(face, eyes, regions.fills_face, regions.fills_eyes)
            refaced, scale = masking.reface(
                defaced, keep, nib.load(ref_in_subject), nib.load(brain_in_subject), fill
            )
            nib.save(refaced, outputs.refaced)
            filled = (("face", regions.fills_face), ("eyes", regions.fills_eyes))
            put_back = " and ".join(part for part, wanted in filled if wanted)
            reporter.step(f"template {put_back} inserted (intensity scale {scale:.3g})")

        # The face is already removed. Save the rotation part of the affine; unless switched
        # off, write the images in template orientation (header only, no resampling).
        tal = TalReorientation.from_affine_matrix(tx.affine_lps, template)
        tal.write_transforms(subject, outputs.txn_itk, outputs.txn_fsl)
        if options.reorient:
            input_crop = tal.write_images(outputs.tal_pairs(), options.crop)[0]
            if input_crop is not None:
                reporter.cropped(input_crop)
            reporter.step("reorientation (header only) and ITK/FSL transforms")
        else:
            reporter.step("ITK/FSL transforms (image not reoriented)")

        # The QC page is written last: a problem with it must not stop the defacing.
        if outputs.qc:
            try:
                qc.write_page(
                    outputs.qc, subject.name, defaced, refaced, fill,
                    [(name, nib.load(path)) for name, path in qc_extras],
                )
                reporter.step("QC page")
            except Exception as problem:  # noqa: BLE001 (any failure here is only a warning)
                reporter.warn(f"No QC page: {type(problem).__name__}: {problem}")
                outputs = replace(outputs, qc=None)

    reporter.end()
    return outputs
