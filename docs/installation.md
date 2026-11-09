# Installation

FaceOff needs Python 3.12 or newer, and a way to run ANTs: ANTs itself on your PATH, Docker running, or Apptainer (or Singularity) installed. Without your own ANTs it runs ANTs from a container image, so you don't have to install it.

## venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install faceoff-mri
faceoff --help
```

## conda / mamba

```bash
conda create -n faceoff python=3.12
conda activate faceoff
pip install faceoff-mri
faceoff --help
```

## The development version, or a source checkout

For the newest code on GitHub instead of the last release: `pip install "git+https://github.com/srikash/FaceOff.git"`. From a checkout:

```bash
git clone https://github.com/srikash/FaceOff.git
cd FaceOff
pip install .
faceoff --help
```

You can also run it from the checkout without installing it, as long as its dependencies are installed: `python -m faceoff --help`.

## If you already have ANTs

When `antsAI`, `antsRegistration`, `antsApplyTransforms`, and `ConvertTransformFile` are all on your PATH, FaceOff uses them directly. It downloads no image and needs no container engine. The log says which ANTs it found and warns if the version is not 2.6.5, the one FaceOff is tested with. Versions before 2.3.3 do not know the option that makes the warped masks 8-bit; FaceOff checks this once per scan (for your own ANTs and for an image given with `--sif`) and leaves the option out, so such an ANTs works but uses more memory for the masks.

To choose for yourself, use `--engine local` (your install, or an error naming the missing tools) or `--engine docker`.

## The package name

The package on PyPI is `faceoff-mri`; the command it installs is `faceoff`. Do not use `pip install faceoff`: that name belongs to a different program (a hockey app), and its files go in the same `faceoff` folder as FaceOff's, so they overwrite each other. If `pip show faceoff` finds anything, run `pip uninstall faceoff` first.

## The FaceOff container image

A ready-made image has FaceOff and ANTs 2.6.5 inside, so you need nothing else but Docker or Apptainer. It is published with each release as `ghcr.io/srikash/faceoff` (a public package, with the tags `latest` and the version, such as `1.9.8.post1`), for 64-bit Intel and AMD processors only (on an Apple-silicon Mac it runs under emulation, slowly).

```bash
cd /path/to/your/scans
docker run --rm --init --user "$(id -u):$(id -g)" -v "$PWD":/data \
    ghcr.io/srikash/faceoff:latest -i sub-01_T1w.nii.gz
```

The outputs appear next to the scan, owned by you. `--user` stops them being owned by root, and `--init` lets Ctrl-C and `docker stop` end the run cleanly. The folder you mount must be writable: FaceOff keeps its working files in a hidden folder beside the scan while it runs. With Apptainer or Singularity, from the folder with your scans:

```bash
apptainer run --cleanenv docker://ghcr.io/srikash/faceoff:latest -i sub-01_T1w.nii.gz
```

`--cleanenv` keeps your own `PATH` and library settings out of the container. Apptainer converts the Docker image itself, so there is no separate file to download: `apptainer pull faceoff.sif docker://ghcr.io/srikash/faceoff:<version>`, then `apptainer run --cleanenv faceoff.sif -i sub-01_T1w.nii.gz`.

To build it yourself from a checkout: `docker build -t faceoff .`

## The ANTs image

You only need this without your own ANTs and without the FaceOff image above.

FaceOff pulls `antsx/ants:2.6.5` the first time you run it. To fetch it in advance:

```bash
docker pull antsx/ants:2.6.5
```

## On a cluster: Apptainer or Singularity

Most clusters don't allow Docker, but many have Apptainer, or Singularity under its older name. Add `--engine apptainer`:

```bash
faceoff -i sub-01_T1w.nii.gz --engine apptainer
```

The first run downloads the ANTs image and saves it as `faceoff/ants-2.6.5.sif` in your cache folder (`$XDG_CACHE_HOME` if set, usually `~/.cache`). Later runs reuse that file. FaceOff uses the `apptainer` command, or `singularity` if that's what your system has. It needs Apptainer 1.1 or newer, or SingularityCE 3.9 or newer.

If the compute nodes can't reach the internet, pull the image yourself on a login node and point FaceOff at the file with `--sif` (which implies `--engine apptainer`):

```bash
apptainer pull ants.sif docker://antsx/ants:2.6.5
faceoff -i sub-01_T1w.nii.gz --sif ants.sif
```

Inside the container, ANTs can read only the folders your files are in, and can write only to FaceOff's temporary folder. Your home folder and environment stay outside.

## The template files

They come with the installed package. See [the template](template.md) for running from a checkout or using your own folder.

[Back to the README](../README.md)
