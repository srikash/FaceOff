# Development

```bash
uv run ruff format --check
uv run ruff check
uv run mypy .
uv run pytest
```

Building the package downloads the template files from Zenodo once, into `faceoff/data/` (git ignores that folder).

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
