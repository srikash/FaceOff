import base64
import io
import re

import nibabel as nib
import numpy as np
from PIL import Image

from faceoff import qc


def _head(shape=(40, 30, 30), value=100.0):
    """A bright box in the middle of an otherwise empty volume."""
    data = np.zeros(shape, np.float32)
    data[10:30, 5:25, 5:25] = value
    return nib.Nifti1Image(data, np.eye(4))


def _page(tmp_path, *args, **kwargs):
    path = tmp_path / "scan_faceoff_qc.html"
    qc.write_page(path, "scan.nii.gz", *args, **kwargs)
    return path.read_text()


def _gif_of(html: str, index: int = 0) -> Image.Image:
    encoded = re.findall(r"data:image/gif;base64,([A-Za-z0-9+/=]+)", html)[index]
    return Image.open(io.BytesIO(base64.b64decode(encoded)))


def _titles(html: str) -> list[str]:
    return re.findall(r"<span>(.*?)</span>", html)


def test_the_interface_is_one_function():
    assert [name for name in vars(qc) if not name.startswith("_") and callable(getattr(qc, name))
            and getattr(getattr(qc, name), "__module__", "") == "faceoff.qc"] == ["write_page"]


def test_a_defaced_image_alone_gives_one_title_and_a_gif_at_the_set_frame_rate(tmp_path):
    html = _page(tmp_path, _head())
    assert html.count("<img") == 1
    assert _titles(html) == ["defaced"]
    assert "repeat(1,1fr)" in html
    gif = _gif_of(html)
    assert gif.info["duration"] == 1000 // qc.FPS
    assert 1 < gif.n_frames <= qc.TARGET_FRAMES


def test_a_refaced_image_adds_a_second_panel_after_the_defaced_one(tmp_path):
    part = nib.Nifti1Image((_head().get_fdata() > 0).astype(np.uint8), np.eye(4))
    html = _page(tmp_path, _head(), _head(), part)
    assert _titles(html) == ["defaced", "refaced"]
    assert "repeat(2,1fr)" in html
    one = _page(tmp_path, _head())
    assert _gif_of(html).width == 2 * _gif_of(one).width


def test_each_extra_gets_its_own_defaced_only_gif_and_a_4d_extra_shows_its_first_volume(tmp_path):
    four_d = nib.Nifti1Image(np.stack([_head().get_fdata()] * 3, axis=-1), np.eye(4))
    html = _page(tmp_path, _head(), extras=[("inv1.nii.gz", _head()), ("echoes.nii.gz", four_d)])
    assert html.count("<img") == 3
    assert _titles(html) == ["defaced", "defaced", "defaced"]
    assert "inv1.nii.gz" in html and "echoes.nii.gz" in html


def test_a_fine_scan_does_not_make_a_longer_gif(tmp_path):
    fine = nib.Nifti1Image(
        np.repeat(np.asarray(_head().dataobj), 4, axis=0), np.diag([0.25, 1, 1, 1])
    )
    assert _gif_of(_page(tmp_path, fine)).n_frames <= qc.TARGET_FRAMES


def test_an_empty_image_does_not_crash(tmp_path):
    empty = nib.Nifti1Image(np.zeros((6, 5, 4), np.float32), np.eye(4))
    assert _gif_of(_page(tmp_path, empty)).n_frames >= 1


def test_the_colour_tables_start_at_black_and_dark_blue():
    assert tuple(qc.MAGMA[0]) == (0, 0, 4)
    assert tuple(qc.TURBO[0]) == (48, 18, 59)
    assert qc.MAGMA.shape == qc.TURBO.shape == (256, 3)
