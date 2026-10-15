# Glossary

The words FaceOff's code and documentation use, and what they mean.

- **Deface mask** (`_defaceMask`): 1 where the scan is kept, 0 where it was removed (the face, and the eyes with `--enucleate` or `--renucleate`).
- **Face mask**: the template's mask of the face, 1 over the region to remove. It is moved onto each scan by the registration.
- **Eye mask**: the template's mask of the eyes, 1 over the eyes. It is used with `--enucleate` and `--renucleate`.
- **Reface**: fill the removed face with the template's face, scaled to the scan's brightness (`--reface`).
- **Enucleate**: remove the eyes as well as the face (`--enucleate`).
- **Renucleate**: remove the eyes and fill them with the template's eyes (`--renucleate`; `--reface --enucleate` does the same, plus the face).
- **Fill**: put template voxels into a removed region (the face, the eyes, or both). The filled image is written as `_refaced`.
- **Regions** (`faceoff/regions.py`): works out once, from `--reface`, `--enucleate`, `--renucleate`, and `--syn`, which regions are removed, which are filled, and which registration moves each mask. Every other part of FaceOff asks it.
- **Affine registration**: rigid, then affine, fitted inside the brain with mutual information (MI). It is always run, and moves the face mask by default.
- **Nonlinear brain registration** (`--syn`): SyN over the whole head with MI, then inside the brain with cross-correlation (CC). With `--syn` it moves the face mask instead of the affine.
- **Nonlinear face registration**: SyN over the face with MI, starting from the registrations above. It moves the eye mask, and the template face and eyes that fill the removed regions.
- **Stage** (`AFFINE`, `NONLINEAR_BRAIN`, `NONLINEAR_FACE`): which of those three registrations moves a template image onto the scan. Each image is moved by one ANTs call with the whole chain of transforms, so it is resampled once.
- **Template orientation** (`_tal_` files): the scan rotated to line up with the template by changing only its header; the voxels are not resampled.
- **Extra images** (`--extra-images`): other images from the same session and scanner space (other MP2RAGE images, GRE echoes). They get the same masks, moved onto their own voxel grid.
- **Scan to deface** (`faceoff/inputs.py`): one scan and its extra images, with every file already checked. All files given are checked before the first scan starts, and every problem is listed at once.
- **Stand-in registration** (`tests/conftest.py`): used only by the tests. It moves template images with a known affine, without ANTs.
