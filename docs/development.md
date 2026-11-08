# Development

```bash
uv run ruff format --check
uv run ruff check
uv run mypy .
uv run pytest
```

Building the package downloads the template files from Zenodo once, into `faceoff/data/` (git ignores that folder).

## Continuous integration and releases

- `.github/workflows/ci.yml` runs on pull requests and on pushes to `v2.0.0`: formatting, lint and types, the tests on Python 3.12, 3.13 and 3.14, and a build of the package that `scripts/check_dist.py` inspects (the wheel must hold the five template files and the MNI notice; the source archive must hold no scans). Run the same commands locally with `uv sync --locked` and the four lines above.
- `.github/workflows/container.yml` builds the Docker image from the `Dockerfile` and checks it (the version, the bundled template, only five NIfTI files inside, ANTs finds its libraries). On a `v*` tag it also pushes `ghcr.io/srikash/faceoff:<version>` and `:latest`, and an Apptainer image `…:<version>-sif`. The `Dockerfile` copies in only the four ANTs tools FaceOff runs and the libraries they load, from `antsx/ants:2.6.5`; keep that version in step with `ANTS_IMAGE` in `faceoff/ants.py` (a test checks it). `.dockerignore` is an allowlist so that no scan can enter an image.
- `.github/workflows/release.yml` runs on a `v*` tag: it stops if the tag does not match the version in `pyproject.toml`, runs the tests, builds the package, creates the GitHub release (which is what Zenodo archives), and publishes to PyPI only when the repository variable `PUBLISH_TO_PYPI` is `true`.
- To release: change the version in `pyproject.toml`, `CITATION.cff`, the README badge and `docs/citation.md`; merge; then `git tag vX.Y.Z && git push origin vX.Y.Z`.
- One-time setup for PyPI: on pypi.org add a pending publisher for project `faceoff-mri` (owner `srikash`, repository `FaceOff`, workflow `release.yml`, environment `pypi`); in the GitHub repository create the environment `pypi` and the variable `PUBLISH_TO_PYPI` = `true`. Make the `ghcr.io/srikash/faceoff` package public after its first push.
- Dependabot (`.github/dependabot.yml`) only works from the default branch, so it starts once these files are on `master`.

```
faceoff/cli.py          the faceoff command and its help screen
faceoff/images.py       reads NIfTI files (NIfTI-1 and NIfTI-2)
faceoff/inputs.py       checks every scan, extra image, and the thread count before anything runs
faceoff/deface.py       defaces one scan from start to finish
faceoff/regions.py      what happens to the face and eyes, worked out once from the flags
faceoff/registration.py the ANTs registration, and moving template images onto the scan
faceoff/qc.py           the QC page: sagittal GIFs of the defaced and refaced scans
faceoff/masking.py      removing the face and eyes, and inserting the template face and eyes
faceoff/reorient.py     template orientation (header only) and the ITK/FSL transforms
faceoff/messages.py     what is printed in the terminal
faceoff/ants.py         running ANTs: your own install, Docker, or Apptainer
faceoff/scratch.py      the hidden temporary folder (.faceoff-…) each run makes beside the scan
faceoff/template.py     the template: its files, brain centre and crop range; template_files.py downloads it
bundle_template.py      puts the template files into the pip package when it is built
tests/                  automated tests
```

[Back to the README](../README.md)
