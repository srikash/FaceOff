# FaceOff [![Version](https://img.shields.io/badge/version-2.0.0-purple.svg)](https://github.com/srikash/FaceOff/releases/tag/v2.0.0) [![Licence](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE) [![DOI](https://zenodo.org/badge/307797054.svg)](https://zenodo.org/badge/latestdoi/307797054)

Deface anatomical MRI scans using ANTs in Docker. FaceOff blanks out the face and ears and leaves the brain alone. By default it also writes a copy reoriented to MNI152 template space (header only, no resampling), and `--reface` can put the template's face in place of the removed one.

## Install

You need Python 3.12 or newer, and Docker running. You don't need to install ANTs.

```bash
pip install faceoff
faceoff --help
```

Conda, source checkouts, and the ANTs image: [docs/installation.md](docs/installation.md).

## Quick start

```bash
faceoff -i sub-01_T1w.nii.gz                    # deface and reorient
faceoff -i sub-01_T1w.nii.gz --reface           # also put a face back
faceoff --batch sub-*_T1w.nii.gz                # several scans, one after another
faceoff -i sub-01_UNIT1.nii.gz --extra-images sub-01_inv-*_MP2RAGE.nii.gz   # MP2RAGE or GRE echoes
```

Outputs go next to the input: `_defaced`, `_defaceMask`, their `_tal_` copies in template orientation, and the `_txn-to-tal` ITK and FSL transforms. A default run takes about 10 seconds on a 12-core workstation; `--reface` takes about 3 minutes.

## More

- [Usage](docs/usage.md): every option, `--extra-images` or `--batch`, workflows, run times
- [Outputs](docs/outputs.md): what each file contains
- [The template](docs/template.md): where the files come from, and the MNI licence
- [Development](docs/development.md): tests and code layout
- [Citation](docs/citation.md): references for FaceOff, the MNI template, and ANTs

## Licence and citation

FaceOff is released under the [MIT licence](LICENSE). The template files keep the [MNI licence](faceoff/COPYING-MNI).

If you use FaceOff, please cite it (Zenodo DOI above, or `CITATION.cff`), the MNI ICBM152 template, and ANTs. The references are in [docs/citation.md](docs/citation.md).
