# Outputs

For an input called `scan.nii.gz`, FaceOff writes these files next to it.

| File | Contents |
| --- | --- |
| `scan_defaceMask.nii.gz` | 1 where data is kept, 0 over the face (and the eyes, with `--enucleate` or `--renucleate`). |
| `scan_defaced.nii.gz` | Your scan with the face (and the eyes, with `--enucleate` or `--renucleate`) removed, in its original orientation and data type. |
| `scan_tal_defaced.nii.gz` | The same, in template orientation (unless you pass `--no-reorient`). |
| `scan_tal_defaceMask.nii.gz` | The deface mask in template orientation (unless you pass `--no-reorient`). |
| `scan_refaced.nii.gz` | Your scan with the template face inserted (with `--reface`), the template eyes (with `--renucleate`), or both. |
| `scan_tal_refaced.nii.gz` | The refaced scan in template orientation (with `--reface` or `--renucleate`, and not with `--no-reorient`). |
| `scan_faceoff_qc.html` | A QC page (unless you pass `--no-qc`): a 10 fps GIF through the sagittal slices of `scan_defaced`, next to `scan_refaced` when that is written, with the template part of the refaced image in turbo. Extra images get a defaced-only GIF each. Open it in any browser. |
| `scan_txn-to-tal_itk.tfm` | The rotation to template orientation, as an ITK transform. |
| `scan_txn-to-tal_fsl.mat` | The same rotation, as an FSL matrix. |
| `extra_defaced.nii.gz`, `extra_tal_defaced.nii.gz` | For each image given with `--extra-images`, written next to that image. |

Extra images may have a different resolution from `-i`, as long as they come from the same session and scanner space. FaceOff places the mask on each one's own grid.

The refaced image is not the person's own face. It is the template's, scaled to the brightness of your scan.

[Back to the README](../README.md)
