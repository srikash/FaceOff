# Usage

Input files must be `.nii` or `.nii.gz`. Outputs are written next to the input file.

## Options

| Option | What it does |
| --- | --- |
| `-i`, `--input FILE` | The scan to deface. |
| `--batch FILES` | Several separate scans, each registered and defaced on its own. If ANTs fails on one, or a file is missing, the others still run. Use this or `-i`, not both. |
| `--extra-images FILES` | Other images from the same session and scanner space as `-i`: for example the other MP2RAGE images, or the echoes of a multi-echo GRE (4D files are fine). They get the same deface mask and reorientation as `-i`, but no new face. Use with `-i`, not `--batch`. |
| `-n`, `--threads N` | How many CPU threads ANTs may use. The default is `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` if you have set it, otherwise every core. |
| `--reorient` / `--no-reorient` | Write the defaced scan and its deface mask in template orientation (the default). With `--no-reorient` you still get the transform files, but no reoriented images. |
| `--crop` / `--no-crop` | Trim the reoriented images to template slices 70 to 263 along z (the default). Whole slices are dropped, and nothing is resampled. |
| `--reface` | Also write a refaced image, with the template's face filling the removed region. |
| `--syn` | Not required, and included for completeness. Adds a slower registration and uses its result for the deface mask. The default registration already gives almost the same mask. |
| `--engine docker` / `--engine apptainer` | Run ANTs in Docker (the default) or in Apptainer. Apptainer falls back to the `singularity` command. See [installation](installation.md#on-a-cluster-apptainer-or-singularity). |
| `--sif FILE` | An Apptainer image file of ANTs to use, for example one you made with `apptainer pull`. Implies `--engine apptainer`. |
| `--version` | Print the version and exit. |
| `-h`, `--help` | Show the options and a short usage guide. |

Reorientation changes only the image header. No voxel values are resampled or interpolated.

Both `--batch` and `--extra-images` take file names separated by commas, spaces, or both, so a wildcard such as `sub-*_T1w.nii.gz` works.

## `--extra-images` or `--batch`?

They look alike, but they do different jobs, and you can't use them together.

| | `-i` with `--extra-images` | `--batch` |
| --- | --- | --- |
| For | Other images from the same session as `-i`: MP2RAGE INV1, INV2, and UNI, or GRE echoes (4D is fine) | Separate scans, such as one T1w for each subject |
| Registered | Once, on the `-i` scan | Once for every scan |
| Deface mask | The same mask for every image | Each scan gets its own |
| With `--reface` | Only the `-i` scan is refaced | Every scan is refaced |
| If one fails | The whole run stops | The other scans still run |
| Example | `faceoff -i sub-01_UNIT1.nii.gz --extra-images sub-01_inv-*_MP2RAGE.nii.gz` | `faceoff --batch sub-*_T1w.nii.gz` |

To deface many MP2RAGE or multi-echo GRE sessions, run FaceOff once per session, because `--batch` can't take extra images. A shell loop does it:

```bash
for uni in sub-*_UNIT1.nii.gz; do
  faceoff -i "$uni" --extra-images "${uni%_UNIT1.nii.gz}"_inv-*_MP2RAGE.nii.gz
done
```

## Choosing a workflow

| Need | Command | Main outputs |
| --- | --- | --- |
| Deface and reorient to template space | `faceoff -i scan.nii.gz` | `_defaced`, `_tal_defaced`, `_defaceMask`, `_tal_defaceMask`, transform files |
| Deface only, keep the original orientation | `faceoff -i scan.nii.gz --no-reorient` | `_defaced`, `_defaceMask`, transform files |
| Deface and keep the original slice range | `faceoff -i scan.nii.gz --no-crop` | `_defaced`, `_tal_defaced` and `_tal_defaceMask` (uncropped), `_defaceMask`, transform files |
| Deface and put a face back | `faceoff -i scan.nii.gz --reface` | the files above, plus `_refaced` and `_tal_refaced` |
| Deface MP2RAGE or multi-echo GRE images together | `faceoff -i uni.nii.gz --extra-images inv1.nii.gz,inv2.nii.gz` | the files above, plus `_defaced` and `_tal_defaced` for each extra image |

## Run time

On a 12-core workstation, a 1 mm isotropic scan takes about 10 seconds with the defaults, plus a few seconds for each extra image. `--reface` takes about 3 minutes. Adding `--syn` takes about 7 minutes more. Pass `-n` to use fewer cores.

[Back to the README](../README.md)
