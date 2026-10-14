# Installation

FaceOff needs Python 3.12 or newer, and Docker running.

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

## The template files

They come with `pip install faceoff`. See [the template](template.md) for running from a checkout or using your own folder.

[Back to the README](../README.md)
