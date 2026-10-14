# Outputs

For an input called `scan.nii.gz`, FaceOff writes these files next to it.

| File | Contents |
| --- | --- |
| `scan_defaceMask.nii.gz` | 1 where data is kept, 0 over the face and ears. |
| `scan_defaced.nii.gz` | Your scan with the face removed, in its original orientation. |
| `scan_tal_defaced.nii.gz` | The same, in template orientation (unless you pass `--no-reorient`). |
| `scan_tal_defaceMask.nii.gz` | The deface mask in template orientation (unless you pass `--no-reorient`). |
| `scan_refaced.nii.gz` | Your scan with the template face inserted (only with `--reface`). |
| `scan_tal_refaced.nii.gz` | The refaced scan in template orientation (only with `--reface`, and not with `--no-reorient`). |
| `scan_txn-to-tal_itk.tfm` | The rotation to template orientation, as an ITK transform. |
| `scan_txn-to-tal_fsl.mat` | The same rotation, as an FSL matrix. |
| `extra_defaced.nii.gz`, `extra_tal_defaced.nii.gz` | For each image given with `--extra-images`, written next to that image. |

Extra images may have a different resolution from `-i`, as long as they come from the same session and scanner space. FaceOff places the mask on each one's own grid.

The refaced image is not the person's own face. It is the template's, scaled to the brightness of your scan.

[Back to the README](../README.md)
