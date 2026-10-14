# The template and the MNI licence

FaceOff registers your scan to a modified version of the MNI ICBM152 2020 extended symmetric template. The four modified files (about 7.7 MB) are published on [Zenodo](https://doi.org/10.5281/zenodo.23328835).

## Where FaceOff finds the files

- `pip install faceoff` includes them, so there is nothing more to download.
- If you run FaceOff straight from a checkout without installing it (`python -m faceoff`), it downloads the files from Zenodo the first time, checks them against their published checksums, and keeps them in `faceoff/zenodo-23328835/` inside your cache folder (`$XDG_CACHE_HOME` if set, usually `~/.cache`).
- Set `FACEOFF_TEMPLATE_DIR` to use a folder of your own.

## Licence

The original template is copyright 1993 to 2020 Louis Collins, McConnell Brain Imaging Centre, Montreal Neurological Institute, McGill University. Its licence lets you use, copy, modify, and distribute it for any purpose without fee, provided the copyright notice appears in all copies. It comes with no warranty. The full notice is in [`faceoff/COPYING-MNI`](../faceoff/COPYING-MNI), and it applies to the modified files too.

[Back to the README](../README.md)
