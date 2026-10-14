# FaceOff [![Version](https://img.shields.io/badge/version-2.0.0-purple.svg)](https://github.com/srikash/FaceOff/releases/tag/v2.0.0) [![Licence](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE) [![DOI](https://zenodo.org/badge/307797054.svg)](https://zenodo.org/badge/latestdoi/307797054)

Deface anatomical MRI scans with ANTs (your own install, Docker, or Apptainer). It removes the face and, if you ask, puts a template face in its place. It can also remove the eyes and put template eyes back.

Other features include rotation to template orientation and automatic cropping, all done with no interpolation.

- `--extra-images` gives other images from the same session (MP2RAGE, multi-echo GRE) the same mask.
- Every run writes an HTML page of sagittal GIFs of the defaced and refaced scans, for a quick visual check (`--no-qc` turns it off).
- `--batch` defaces many scans in one go.
- FaceOff uses the ANTs on your PATH when it finds one. Otherwise it runs ANTs in Docker, or in Apptainer or Singularity with `--engine apptainer` or `--sif`, for clusters without Docker.

<p align="center">
  <img src="https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/faceoff.gif" alt="Face swap scene from the film Face/Off">
  <br>
  <em>Face/Off (1997)</em>
</p>

## Install

You need Python 3.12 or newer, and ANTs 2.6 on your PATH, Docker, or Apptainer (or Singularity).

```bash
pip install faceoff
faceoff --help
```

Conda, source checkouts, clusters with Apptainer, and the ANTs image: [docs/installation.md](docs/installation.md).

## Quick start

```bash
faceoff -i sub-01_T1w.nii.gz                    # deface and reorient
faceoff -i sub-01_T1w.nii.gz --reface           # also put a face back
faceoff -i sub-01_T1w.nii.gz --enucleate        # remove the eyes too
faceoff -i sub-01_T1w.nii.gz --renucleate       # remove the eyes and put template eyes back
faceoff --batch sub-*_T1w.nii.gz                # several scans, one after another
faceoff -i sub-01_UNIT1.nii.gz --extra-images sub-01_inv-*_MP2RAGE.nii.gz   # MP2RAGE or GRE echoes
```

Outputs go next to the input: `_defaced`, `_defaceMask`, their `_tal_` copies in template orientation, the `_txn-to-tal` ITK and FSL transforms, and a `_faceoff_qc.html` page for checking the result. A default run takes about 10 seconds on a 12-core workstation; `--reface` and `--renucleate` take about 3 minutes.

## More

- [Usage](docs/usage.md): every option, `--extra-images` or `--batch`, workflows, run times
- [Outputs](docs/outputs.md): what each file contains
- [The template](docs/template.md): where the files come from, and the MNI licence
- [Development](docs/development.md): tests and code layout
- [Citation](docs/citation.md): references for FaceOff, the MNI template, and ANTs

## Licence and citation

FaceOff is released under the [MIT licence](LICENSE). The template files keep the [MNI licence](faceoff/COPYING-MNI).

If you use FaceOff, please cite it (Zenodo DOI above, or `CITATION.cff`), the MNI ICBM152 template, and ANTs. The references are in [docs/citation.md](docs/citation.md).
