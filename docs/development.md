# Development

```bash
pip install -e . pytest ruff
python -m pytest tests
ruff check --select F,E9 .
```

The editable install downloads the template files from Zenodo once, into `faceoff/data/` (git ignores that folder).

```
faceoff/cli.py          the faceoff command and its help screen
faceoff/deface.py       defaces one scan from start to finish
faceoff/registration.py the ANTs registration, and moving template images onto the scan
faceoff/masking.py      removing the face and inserting the template face
faceoff/reorient.py     template orientation (header only) and the ITK/FSL transforms
faceoff/messages.py     what is printed in the terminal
faceoff/ants.py         running ANTs in Docker
faceoff/scratch.py      the temporary folder for each run
faceoff/template.py     the template: its files, brain centre and crop range; template_files.py downloads it
bundle_template.py      puts the template files into the pip package when it is built
tests/                  automated tests
registration_review/    the exact ANTs commands each mode runs
```

[Back to the README](../README.md)
