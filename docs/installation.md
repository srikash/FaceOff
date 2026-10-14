# Installation

FaceOff needs Python 3.12 or newer, and either Docker running or Apptainer (or Singularity) installed. It runs ANTs from a container image, so you don't install ANTs yourself.

## venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install faceoff
faceoff --help
```

## conda / mamba

```bash
conda create -n faceoff python=3.12
conda activate faceoff
pip install faceoff
faceoff --help
```

## From a source checkout

```bash
git clone https://github.com/srikash/FaceOff.git
cd FaceOff
pip install .
faceoff --help
```

You can also run it from the checkout without installing it, as long as its dependencies are installed: `python -m faceoff --help`.

## The ANTs image

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

They come with `pip install faceoff`. See [the template](template.md) for running from a checkout or using your own folder.

[Back to the README](../README.md)
