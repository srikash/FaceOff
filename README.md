# FaceOff [![Version](https://img.shields.io/badge/version-2.0.0-purple.svg)](https://github.com/srikash/FaceOff/releases/tag/v2.0.0) [![Licence](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE) [![DOI](https://zenodo.org/badge/307797054.svg)](https://zenodo.org/badge/latestdoi/307797054)

Deface anatomical MRI scans using ANTs in a Docker container, with optional reorientation to MNI152 template space and optional replacement of the face with the template's.

## Table of contents

- [Why FaceOff?](#why-faceoff)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Options](#options)
- [Choosing a workflow](#choosing-a-workflow)
- [Outputs](#outputs)
- [Run time](#run-time)
- [Templates and the MNI licence](#templates-and-the-mni-licence)
- [Development](#development)
- [Licence](#licence)
- [Citation](#citation)

## Why FaceOff?

A head scan shows the person's face, so sharing the scan shares their identity. FaceOff finds the face and ears on your scan and blanks them out. The brain is left alone.

By default it also saves how your scan sits relative to the MNI152 template and writes a copy reoriented to match. If you would rather the scan still looked like a head, `--reface` fills the blanked region with the template's face.

You do not need to install ANTs. FaceOff runs it from a Docker image.

## Installation

FaceOff needs Python 3.12 or newer, and Docker running.

### venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install faceoff
faceoff --help
```

### conda / mamba

```bash
conda create -n faceoff python=3.12
conda activate faceoff
pip install faceoff
faceoff --help
```

### From a source checkout

```bash
git clone https://github.com/srikash/FaceOff.git
cd FaceOff
pip install .
faceoff --help
```

You can also run it from the checkout without installing: `python -m faceoff --help`.

### The ANTs image

FaceOff pulls `antsx/ants:2.6.5` the first time you run it. To fetch it in advance:

```bash
docker pull antsx/ants:2.6.5
```

### The template files

The four template files (about 7.7 MB, a modified version of the MNI152 2020 template) come with `pip install faceoff`, so there is nothing more to download. They are published on [Zenodo](https://doi.org/10.5281/zenodo.23328835).

If you run FaceOff straight from a checkout without installing it (`python -m faceoff`), it downloads the files from Zenodo the first time, checks them against their published checksums, and keeps them in `~/.cache/faceoff/zenodo-23328835/`. Set `FACEOFF_TEMPLATE_DIR` to use a folder of your own.

## Quick start

```bash
faceoff -i sub-01_T1w.nii.gz
faceoff -i sub-01_T1w.nii.gz --reface
faceoff -i sub-01_T1w.nii.gz --no-reorient
faceoff -i sub-01_T1w.nii.gz --no-crop -n 4
faceoff --batch sub-01_T1w.nii.gz,sub-02_T1w.nii.gz
faceoff -i sub-01_UNIT1.nii.gz --extra-images sub-01_inv-1_MP2RAGE.nii.gz,sub-01_inv-2_MP2RAGE.nii.gz
```

Input files must be `.nii` or `.nii.gz`. Outputs are written next to the input file.

## Options

| Option | What it does |
| --- | --- |
| `-i`, `--input FILE` | The scan to deface. |
| `--batch FILES` | Several scans, separated by commas, processed one after another. If one fails, the rest still run. Use this or `-i`, not both. |
| `--extra-images FILES` | Other images from the same session and scanner space as `-i`, separated by commas: for example the other MP2RAGE images, or the echoes of a multi-echo GRE (4D files are fine). They get the same deface mask and reorientation as `-i`, but no new face. Use with `-i`, not `--batch`. |
| `-n`, `--threads N` | Number of threads. The default is every core on the machine. |
| `--reorient` / `--no-reorient` | Write the defaced scan in template orientation (the default). With `--no-reorient` you still get the transform files, but no reoriented image. |
| `--crop` / `--no-crop` | Trim the reoriented image to template slices 70 to 263 along z (the default). Whole slices are dropped, and nothing is resampled. |
| `--reface` | Also write a refaced image, with the template's face filling the removed region. |
| `--syn` | Not required, and included for completeness. Adds a slower registration and uses its result for the deface mask. The default registration already gives almost the same mask. |
| `--version` | Print the version and exit. |
| `-h`, `--help` | Show the options and a short usage guide. |

Reorientation changes only the image header. No voxel values are resampled or interpolated.

## Choosing a workflow

| Need | Command | Main outputs |
| --- | --- | --- |
| Deface and reorient to template space | `faceoff -i scan.nii.gz` | `_defaced`, `_tal_defaced`, `_defaceMask`, `_tal_defaceMask`, transform files |
| Deface only, keep the original orientation | `faceoff -i scan.nii.gz --no-reorient` | `_defaced`, `_defaceMask`, transform files |
| Deface and keep the original slice range | `faceoff -i scan.nii.gz --no-crop` | `_defaced`, `_tal_defaced` and `_tal_defaceMask` (uncropped), `_defaceMask`, transform files |
| Deface and put a face back | `faceoff -i scan.nii.gz --reface` | the files above, plus `_refaced` and `_tal_refaced` |
| Deface MP2RAGE or multi-echo GRE images together | `faceoff -i uni.nii.gz --extra-images inv1.nii.gz,inv2.nii.gz` | the files above, plus `_defaced` and `_tal_defaced` for each extra image |

## Outputs

For an input called `scan.nii.gz`, FaceOff writes these files next to it.

| File | Contents |
| --- | --- |
| `scan_defaceMask.nii.gz` | 1 where data is kept, 0 over the face and ears. |
| `scan_defaced.nii.gz` | Your scan with the face removed, in its original orientation. |
| `scan_tal_defaced.nii.gz` | The same, in template orientation (unless you pass `--no-reorient`). |
| `scan_tal_defaceMask.nii.gz` | The deface mask in template orientation (unless you pass `--no-reorient`). |
| `scan_refaced.nii.gz` | Your scan with the template face inserted (only with `--reface`). |
| `scan_tal_refaced.nii.gz` | The refaced scan in template orientation (only with `--reface`). |
| `scan_txn-to-tal_itk.tfm` | The rotation to template orientation, as an ITK transform. |
| `scan_txn-to-tal_fsl.mat` | The same rotation, as an FSL matrix. |
| `extra_defaced.nii.gz`, `extra_tal_defaced.nii.gz` | For each image given with `--extra-images`, written next to that image. |

Extra images may have a different resolution from `-i`, as long as they come from the same session and scanner space. FaceOff places the mask on each one's own grid.

The refaced image is not the person's own face. It is the template's, scaled to the brightness of your scan.

## Run time

On a 12-core workstation, a 1 mm isotropic scan takes about 10 seconds with the defaults, plus a few seconds for each extra image. `--reface` takes about 3 minutes. Adding `--syn` takes about 7 minutes more. Pass `-n` to use fewer cores.

## Templates and the MNI licence

FaceOff registers your scan to a modified version of the MNI ICBM152 2020 extended symmetric template. The four modified files are published on [Zenodo](https://doi.org/10.5281/zenodo.23328835). The original template is copyright 1993 to 2020 Louis Collins, McConnell Brain Imaging Centre, Montreal Neurological Institute, McGill University. Its licence lets you use, copy, modify, and distribute it for any purpose without fee, provided the copyright notice appears in all copies. It comes with no warranty. The full notice is in [`faceoff/COPYING-MNI`](faceoff/COPYING-MNI), and it applies to the modified files too.

## Development

```bash
pip install -e . pytest ruff
python -m pytest tests
ruff check --select F,E9 .
```

```
faceoff/                command line, ANTs runner, registration, reorientation, face editing, template download
tests/                  unit tests
registration_review/    the exact ANTs commands each mode runs
hatch_build.py          puts the template files into the wheel when it is built
```

## Licence

FaceOff is released under the [MIT licence](LICENSE). The template files keep the MNI licence described above.

## Citation

If you use FaceOff, please cite it using the Zenodo DOI above or the `CITATION.cff` file in this repository. The modified template files are archived at [10.5281/zenodo.23328835](https://doi.org/10.5281/zenodo.23328835).

Please also cite the original MNI template and ANTs:

- Fonov VS, Evans AC, Botteron K, Almli CR, McKinstry RC, Collins DL, and the Brain Development Cooperative Group. Unbiased average age-appropriate atlases for pediatric studies. NeuroImage. 2011;54(1). [doi:10.1016/j.neuroimage.2010.07.033](https://doi.org/10.1016/j.neuroimage.2010.07.033)
- Fonov VS, Evans AC, McKinstry RC, Almli CR, Collins DL. Unbiased nonlinear average age-appropriate brain templates from birth to adulthood. NeuroImage. 2009;47(Suppl 1):S102.
- ANTs: [PubMed 20851191](http://www.ncbi.nlm.nih.gov/pubmed/20851191) and [Frontiers in Neuroinformatics 2013, doi:10.3389/fninf.2013.00039](http://www.frontiersin.org/Journal/10.3389/fninf.2013.00039/abstract).
