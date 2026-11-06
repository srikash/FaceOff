"""Deface one scan from start to finish: register, remove the face (and the eyes, if asked),
put the template's face and eyes back if asked, and reorient."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import nibabel as nib
import numpy as np

from . import masking, qc
from .ants import Container
from .images import load_image
from .inputs import ScanToDeface, strip_extension
from .regions import Regions
from .registration import Stage, Transforms, register
from .reorient import Crop, TalReorientation
from .scratch import Workspace, workspace
from .template import Template


@dataclass(frozen=True)
class Options:
    """The choices for one run. The defaults are the same as the command line's."""

    threads: int
    syn: bool = False
    # Also write the outputs in template orientation (header change only).
    reorient: bool = True
    # Trim those template-orientation outputs to the z range TEMPLATE_CROP_Z_MM. Does nothing
    # without reorient.
    crop: bool = True
    # How reface, enucleate and renucleate combine: see Regions.
    reface: bool = False
    enucleate: bool = False
    renucleate: bool = False
    # Also write a QC page (name_faceoff_qc.html): a GIF of the defaced (and refaced) scan for
    # each image.
    qc: bool = True
    # The template to register to; the tests pass a small synthetic one.
    template: Template = field(default_factory=Template.default)
    container: Container = field(default_factory=Container.default)
    overwrite: bool = False

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


def check_inputs(scans: list[ScanToDeface], options: Options) -> None:
    """Reject runs that cannot work, before any scan is processed: refacing a 4D scan (one
    intensity scale from the first volume would be wrong for the others), and conflicting
    outputs (see check_outputs)."""
    if options.regions.writes_refaced:
        for scan in scans:
            shape = load_image(scan.scan).shape
            if len(shape) > 3 and any(size != 1 for size in shape[3:]):
                raise ValueError(
                    f"{scan.scan.name} is 4D ({'x'.join(map(str, shape))}); refacing needs a 3D "
                    "scan. Deface it without --reface/--renucleate."
                )
    check_outputs(scans, options)


def check_outputs(scans: list[ScanToDeface], options: Options) -> None:
    """Reject conflicting outputs before processing any scan."""
    inputs = {path.resolve() for scan in scans for path in (scan.scan, *scan.extra_images)}
    outputs = [
        path
        for scan in scans
        for path in Outputs.for_input(scan.scan, list(scan.extra_images), options).written()
    ]
    resolved = [path.resolve() for path in outputs]
    input_ids = {(path.stat().st_dev, path.stat().st_ino) for path in inputs if path.exists()}
    output_ids = [(path.stat().st_dev, path.stat().st_ino) for path in outputs if path.exists()]
    if (
        inputs.intersection(resolved)
        or len(set(resolved)) != len(resolved)
        or input_ids.intersection(output_ids)
        or len(set(output_ids)) != len(output_ids)
    ):
        raise ValueError("Output paths conflict with inputs or other outputs.")
    existing = [str(path) for path in outputs if path.exists() or path.is_symlink()]
    if existing and not options.overwrite:
        raise ValueError("Outputs already exist; use --overwrite: " + ", ".join(existing))


class Reporter:
    """Where a run reports its progress. This one stays silent; the command line uses
    `messages.ConsoleReporter`, which prints to the terminal.

    A run calls `begin` once, `step` after each finished step, `warn` for a problem that does
    not stop the run, `qc_failed` if the QC page was not written, `cropped` once if the
    template-orientation outputs are cropped, and `end` once.
    """

    def begin(self, input_file: Path, options: Options, outputs: Outputs) -> None:
        """Called once, before anything is computed."""

    def step(self, message: str) -> None:
        """Called after each step finishes, with a short description of it."""

    def warn(self, message: str) -> None:
        """Called when something optional, such as the QC page, could not be written."""

    def qc_failed(self) -> None:
        """Called when the QC page was not written."""

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
        return load_image(face), None
    eyes = ws.path(f"eye_mask_in_{label}.nii.gz")
    tx.to_subject(template.eye_mask, eyes, regions.eye_mask_stage, reference=reference)
    return load_image(face), load_image(eyes)


def register_with_ants(ws: Workspace, subject: Path, options: Options) -> Transforms:
    """Register the scan to the template with ANTs, run as `options.container` says."""
    ants = options.container.runner(options.threads, scratch=ws.root)
    face = options.regions.needs_face_registration
    return register(ants, ws, subject, options.template, syn=options.syn, face=face)


def run(
    scan: ScanToDeface,
    options: Options,
    reporter: Reporter | None = None,
    registration: Callable[[Workspace, Path, Options], Transforms] = register_with_ants,
) -> Outputs:
    """Deface one scan, and its extra images, and write the outputs next to them. Returns the
    names of the files written. The files were already checked (see inputs.scans_to_deface).

    Extra images are other images from the same session and scanner space (other MP2RAGE
    images, GRE echoes, ...): they get the same deface mask and reorientation, not a face.

    `registration` registers the scan to the template: ANTs by default. The tests pass a
    stand-in that moves template images with a known affine.
    """
    check_inputs([scan], options)
    template = options.template
    subject, extras = scan.scan, list(scan.extra_images)
    reporter = reporter or Reporter()
    outputs = Outputs.for_input(subject, extras, options)
    reporter.begin(subject, options, outputs)

    with workspace() as ws:
        regions = options.regions
        tx = registration(ws, subject, options)
        # The reorientation is worked out now, so a registration that cannot be used (see
        # TalReorientation) stops the run before any file is written.
        tal = TalReorientation.from_affine_matrix(tx.affine_lps, template)
        if options.reorient and options.crop:
            for image_path in (subject, *extras):
                tal.check_crop(load_image(image_path))
        reporter.step("registration to the template")

        # Everything is worked out in memory first, so a problem found along the way leaves no
        # half-written set of files. The template masks mark the region to remove; the deface
        # mask is its inverse.
        face, eyes = _warp_masks(tx, ws, template, regions, "subject")
        if not np.any(np.asanyarray(face.dataobj)):
            raise ValueError("The face mask is empty; the scan was not defaced.")
        keep = masking.keep_mask(face, eyes)
        defaced = masking.deface(load_image(subject), keep)
        reporter.step("deface mask")

        # Extra images may have their own voxel grid, so the masks are warped onto each
        # one's grid rather than reused; on the input's grid this gives the same mask.
        extra_keeps = []
        for n, extra in enumerate(extras):
            extra_face, extra_eyes = _warp_masks(tx, ws, template, regions, f"extra{n}", extra)
            if not np.any(np.asanyarray(extra_face.dataobj)):
                raise ValueError(
                    f"The face mask is empty on {extra.name}, so it was not defaced. Its "
                    "field of view may not include the face, or it is not in the same space "
                    "as the main scan."
                )
            extra_keeps.append(masking.keep_mask(extra_face, extra_eyes))

        refaced = fill = None
        if regions.writes_refaced:
            ref_in_subject = ws.path("template_ref_in_subject.nii.gz")
            brain_in_subject = ws.path("template_brain_in_subject.nii.gz")
            tx.to_subject(template.t1w, ref_in_subject, Stage.NONLINEAR_FACE, "Linear")
            tx.to_subject(template.brain_mask, brain_in_subject, Stage.NONLINEAR_FACE)
            fill = masking.fill_region(face, eyes, regions.fills_face, regions.fills_eyes)
            refaced, scale = masking.reface(
                defaced, keep, load_image(ref_in_subject), load_image(brain_in_subject), fill
            )
            filled = (("face", regions.fills_face), ("eyes", regions.fills_eyes))
            put_back = " and ".join(part for part, wanted in filled if wanted)
            reporter.step(f"template {put_back} inserted (intensity scale {scale:.3g})")

        nib.save(keep, outputs.deface_mask)
        nib.save(defaced, outputs.defaced)
        qc_extras = []
        for extra, extra_keep, target in zip(
            extras, extra_keeps, outputs.extra_defaced, strict=True
        ):
            nib.save(masking.deface(load_image(extra), extra_keep), target)
            if outputs.qc:  # the QC page reads the saved file back, one volume at a time
                qc_extras.append((extra.name, target))
        if refaced is not None:
            assert outputs.refaced is not None  # set whenever regions.writes_refaced
            nib.save(refaced, outputs.refaced)
        reporter.step("face taken… off" + (f" ({len(extras)} extra image(s))" if extras else ""))

        # The face is already removed. Save the rotation part of the affine; unless switched
        # off, write the images in template orientation (header only, no resampling).
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
                    outputs.qc,
                    subject.name,
                    defaced,
                    refaced,
                    fill,
                    [(name, load_image(path)) for name, path in qc_extras],
                )
                reporter.step("QC page")
            except Exception as problem:  # noqa: BLE001 (any failure here is only a warning)
                # A page from an earlier run would show a different defacing; --overwrite
                # already allows replacing it.
                old_page = outputs.qc.exists()
                try:
                    outputs.qc.unlink(missing_ok=True)
                    cleared = " The old page was removed." if old_page else ""
                except OSError as unlink_problem:
                    cleared = f" The old page could not be removed: {unlink_problem}."
                reporter.warn(f"No QC page: {type(problem).__name__}: {problem}.{cleared}")
                outputs = replace(outputs, qc=None)
                reporter.qc_failed()

    reporter.end()
    return outputs
