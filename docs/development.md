# Development

```bash
uv run ruff format --check
uv run ruff check
uv run mypy .
uv run pytest
```

Building the package downloads the template files from Zenodo once, into `faceoff/data/` (git ignores that folder).

## Continuous integration and releases

- `.github/workflows/ci.yml` runs on pull requests and on pushes to `master`: formatting, lint and types, the tests on Python 3.12, 3.13 and 3.14, and a build of the package that `scripts/check_dist.py` inspects (the wheel must hold the five template files and the MNI notice; the source archive must hold no scans). Run the same commands locally with `uv sync --locked` and the four lines above.
- `.github/workflows/container.yml` builds the Docker image from the `Dockerfile` and checks it (the version, the bundled template, only five NIfTI files inside, ANTs finds its libraries). On a `v*` tag it also pushes `ghcr.io/srikash/faceoff:<version>` and `:latest`. The `Dockerfile` copies in only the four ANTs tools FaceOff runs and the libraries they load, from `antsx/ants:2.6.5`; keep that version in step with `ANTS_IMAGE` in `faceoff/ants.py` (a test checks it). `.dockerignore` is an allowlist so that no scan can enter an image.
- `.github/workflows/release.yml` runs on a `v*` tag: it stops if the tag does not match the version in `pyproject.toml`, runs the tests, builds the package, creates the GitHub release (which is what Zenodo archives), and publishes to PyPI (it skips a version that is already there).
- To release: change the version in `pyproject.toml`, `CITATION.cff`, the README badge and `docs/citation.md`, then run `uv lock` (the lock file records the project's version, and `uv sync --locked` in CI, the release and the `Dockerfile` fails if it is stale); merge it to `master`. When CI is green on `master`, its `tag-release` job creates the tag `vX.Y.Z` if it does not exist yet and starts the image and release workflows, so **merging a version change is a release** (a tag pushed by hand also works; a version lower than an existing tag is refused). If a release job fails after the tag exists (the PyPI setup, a network problem), use "Re-run failed jobs" on that run; the tag stays and the same commit is built again. If starting the workflows failed after the tag was pushed, start them by hand: `gh workflow run release.yml --ref vX.Y.Z` and the same for `container.yml`. A fix to the code needs a new version. Once PyPI is live, change the install lines in the README and `docs/installation.md` to `pip install faceoff-mri`. The image, the package and the GitHub release are built by separate workflows, so a failure in one does not stop another from publishing. Release candidates (`v2.0.0-rc1`) are not supported, because the tag must equal the version exactly. A branch named `v2.0.0` would clash with a `v2.0.0` tag (and a tag runs the release workflows), so delete that branch before tagging such a version.
- One-time setup for PyPI: on pypi.org add a pending publisher for project `faceoff-mri` (owner `srikash`, repository `FaceOff`, workflow `release.yml`, environment `pypi`); in the GitHub repository create the environment `pypi`. Until both exist, the PyPI step of a release fails and the others still run (use "Re-run failed jobs" afterwards). Make the `ghcr.io/srikash/faceoff` package public after its first push.

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
