"""The QC page: for each image, a GIF that sweeps through its sagittal slices, so you can check
the removed region by eye. It shows the defaced scan and, when a refaced image is written, the
refaced one (the part filled from the template in turbo). The original scan, face and all, is
not shown.

The colour tables are the 256 steps of matplotlib's magma and turbo, stored here as hex (three
bytes per step) so that only Pillow is needed.
"""

from __future__ import annotations

import base64
import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

FPS = 10
TARGET_FRAMES = 30  # about 3 s per loop, whatever the scan's resolution
PANEL_HEIGHT = 190  # pixels; the width follows the head's shape, so the page stays light
NOISE_FLOOR = 0.05  # of the brightest voxels: dropped, because noise makes GIFs much larger
COLOURS = 64  # per frame

_MAGMA = (
    "00000401000501010601010802010902020b02020d03030f03031204041405041606051806051a07061c08071e090720"
    "0a08220b09240c09260d0a290e0b2b100b2d110c2f120d31130d34140e36150e38160f3b180f3d19103f1a10421c1044"
    "1d11471e114920114b21114e22115024125325125527125829115a2a115c2c115f2d11612f1163311165331067341069"
    "36106b38106c390f6e3b0f703d0f713f0f72400f74420f75440f764510774710784910784a10794c117a4e117b4f127b"
    "51127c52137c54137d56147d57157e59157e5a167e5c167f5d177f5f187f601880621980641a80651a80671b80681c81"
    "6a1c816b1d816d1d816e1e81701f81721f817320817521817621817822817922827b23827c23827e2482802582812581"
    "8326818426818627818827818928818b29818c29818e2a81902a81912b81932b80942c80962c80982d80992d809b2e7f"
    "9c2e7f9e2f7fa02f7fa1307ea3307ea5317ea6317da8327daa337dab337cad347cae347bb0357bb2357bb3367ab5367a"
    "b73779b83779ba3878bc3978bd3977bf3a77c03a76c23b75c43c75c53c74c73d73c83e73ca3e72cc3f71cd4071cf4070"
    "d0416fd2426fd3436ed5446dd6456cd8456cd9466bdb476adc4869de4968df4a68e04c67e24d66e34e65e44f64e55064"
    "e75263e85362e95462ea5661eb5760ec5860ed5a5fee5b5eef5d5ef05f5ef1605df2625df2645cf3655cf4675cf4695c"
    "f56b5cf66c5cf66e5cf7705cf7725cf8745cf8765cf9785df9795df97b5dfa7d5efa7f5efa815ffb835ffb8560fb8761"
    "fc8961fc8a62fc8c63fc8e64fc9065fd9266fd9467fd9668fd9869fd9a6afd9b6bfe9d6cfe9f6dfea16efea36ffea571"
    "fea772fea973feaa74feac76feae77feb078feb27afeb47bfeb67cfeb77efeb97ffebb81febd82febf84fec185fec287"
    "fec488fec68afec88cfeca8dfecc8ffecd90fecf92fed194fed395fed597fed799fed89afdda9cfddc9efddea0fde0a1"
    "fde2a3fde3a5fde5a7fde7a9fde9aafdebacfcecaefceeb0fcf0b2fcf2b4fcf4b6fcf6b8fcf7b9fcf9bbfcfbbdfcfdbf"
)
_TURBO = (
    "30123b32154333184a341b51351e5836215f37246638276d392a733a2d793b2f803c32863d358b3e38913f3b973f3e9c"
    "4040a24143a74146ac4249b1424bb5434eba4451bf4454c34456c74559cb455ccf455ed34661d64664da4666dd4669e0"
    "466be3476ee64771e94773eb4776ee4778f0477bf2467df44680f64682f84685fa4687fb458afc458cfd448ffe4391fe"
    "4294ff4196ff4099ff3e9bfe3d9efe3ba0fd3aa3fc38a5fb37a8fa35abf833adf731aff52fb2f42eb4f22cb7f02ab9ee"
    "28bceb27bee925c0e723c3e422c5e220c7df1fc9dd1ecbda1ccdd81bd0d51ad2d21ad4d019d5cd18d7ca18d9c818dbc5"
    "18ddc218dec018e0bd19e2bb19e3b91ae4b61ce6b41de7b21fe9af20eaac22ebaa25eca727eea42aefa12cf09e2ff19b"
    "32f29835f39438f4913cf58e3ff68a43f78746f8844af8804ef97d52fa7a55fa7659fb735dfc6f61fc6c65fd6969fd66"
    "6dfe6271fe5f75fe5c79fe597dff5680ff5384ff5188ff4e8bff4b8fff4992ff4796fe4499fe429cfe409ffd3fa1fd3d"
    "a4fc3ca7fc3aa9fb39acfb38affa37b1f936b4f836b7f735b9f635bcf534bef434c1f334c3f134c6f034c8ef34cbed34"
    "cdec34d0ea34d2e935d4e735d7e535d9e436dbe236dde037dfdf37e1dd37e3db38e5d938e7d739e9d539ebd339ecd13a"
    "eecf3aefcd3af1cb3af2c93af4c73af5c53af6c33af7c13af8be39f9bc39faba39fbb838fbb637fcb336fcb136fdae35"
    "fdac34fea933fea732fea431fea130fe9e2ffe9b2dfe992cfe962bfe932afe9029fd8d27fd8a26fc8725fc8423fb8122"
    "fb7e21fa7b1ff9781ef9751df8721cf76f1af66c19f56918f46617f36315f26014f15d13f05b12ef5811ed5510ec530f"
    "eb500eea4e0de84b0ce7490ce5470be4450ae2430ae14109df3f08dd3d08dc3b07da3907d83706d63506d43305d23105"
    "d02f05ce2d04cc2b04ca2a04c82803c52603c32503c12302be2102bc2002b91e02b71d02b41b01b21a01af1801ac1701"
    "a91601a71401a41301a112019e10019b0f01980e01950d01920b018e0a018b09028808028507028106027e05027a0403"
)
MAGMA = np.frombuffer(bytes.fromhex(_MAGMA), np.uint8).reshape(256, 3)
TURBO = np.frombuffer(bytes.fromhex(_TURBO), np.uint8).reshape(256, 3)


@dataclass(frozen=True)
class _Panel:
    """One picture in a GIF: a title, the image, and the part of it to draw in turbo."""

    title: str
    image: nib.Nifti1Image
    template_part: nib.Nifti1Image | None = None  # 1 where the template was inserted


@dataclass(frozen=True)
class _Section:
    """One GIF on the page: a name and its panels, side by side."""

    name: str
    panels: list[_Panel]


def _ras(image: nib.Nifti1Image) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Return the first volume in RAS orientation (x right, y anterior, z superior), and the
    voxel size along those axes."""
    while image.ndim > 3:  # a 4D image (GRE echoes, ...): show the first volume, read alone
        image = image.slicer[..., 0]
    canonical = nib.as_closest_canonical(image)
    data = np.asarray(canonical.dataobj, dtype=np.float32)
    zooms = tuple(float(z) for z in canonical.header.get_zooms()[:3])
    return data, zooms


def _extent(counts: np.ndarray, area: int, fraction: float) -> np.ndarray:
    """Indices whose slice holds more than `fraction` of a slice's area; all of them if none."""
    found = np.nonzero(counts > fraction * area)[0]
    return found if found.size else np.arange(counts.size)


def _sweep_gif(panels: list[_Panel]) -> tuple[str, int]:
    """Return the sweep through the sagittal slices as a base64 GIF, and the GIF's width.

    The slices are those that hold the head, about TARGET_FRAMES of them, and the panels are
    cropped to the head and to what was inserted. Panels share one brightness scale.
    """
    volumes = [_ras(panel.image) for panel in panels]
    parts = [_ras(p.template_part)[0] > 0 if p.template_part is not None else None for p in panels]
    shape = volumes[0][0].shape
    positive = np.concatenate([v[v > 0] for v, _ in volumes] + [np.zeros(1, np.float32)])
    top = float(np.percentile(positive, 99.5)) if positive.size > 1 else 1.0
    top = top if top > 0 else 1.0

    bright = np.zeros(shape, bool)
    for (volume, _), part in zip(volumes, parts):
        bright |= volume > 0.3 * top
        if part is not None:
            bright |= part & (volume > 0.3 * top)
    xs = _extent(bright.sum(axis=(1, 2)), shape[1] * shape[2], 0.0046)
    ys = _extent(bright.sum(axis=(0, 2)), shape[0] * shape[2], 0.0008)
    zs = _extent(bright.sum(axis=(0, 1)), shape[0] * shape[1], 0.0008)
    box = (slice(ys.min(), ys.max() + 1), slice(zs.min(), zs.max() + 1))
    zoom_y, zoom_z = volumes[0][1][1], volumes[0][1][2]
    height = PANEL_HEIGHT
    width = max(1, round(height * (ys.size * zoom_y) / (zs.size * zoom_z)))
    step = max(1, math.ceil(xs.size / TARGET_FRAMES))

    frames = []
    for x in range(int(xs.min()), int(xs.max()) + 1, step):
        row = []
        for (volume, _), part in zip(volumes, parts):
            level = np.clip(volume[x][box].T[::-1] / top, 0, 1)
            level[level < NOISE_FLOOR] = 0
            rgb = MAGMA[(level * 255).astype(np.uint8)]
            if part is not None:
                here = part[x][box].T[::-1] & (level > 0.03)
                rgb[here] = TURBO[(level[here] * 255).astype(np.uint8)]
            row.append(Image.fromarray(rgb).resize((width, height), Image.Resampling.BILINEAR))
        ImageDraw.Draw(row[0]).text((4, height - 14), f"x={x}", fill=(220, 220, 220))
        frame = Image.new("RGB", (width * len(row), height))
        for i, picture in enumerate(row):
            frame.paste(picture, (i * width, 0))
        frames.append(frame.quantize(colors=COLOURS, dither=Image.Dither.NONE))
    buffer = io.BytesIO()
    frames[0].save(
        buffer, format="GIF", save_all=True, append_images=frames[1:],
        duration=1000 // FPS, loop=0, optimize=True,
    )
    return base64.b64encode(buffer.getvalue()).decode(), width * len(panels)


def write_page(
    path: Path,
    title: str,
    defaced: nib.Nifti1Image,
    refaced: nib.Nifti1Image | None = None,
    template_part: nib.Nifti1Image | None = None,
    extras: Sequence[tuple[str, nib.Nifti1Image]] = (),
) -> None:
    """Write the QC page, one self-contained HTML file.

    It has a GIF for the scan, titled `title`, with the defaced image and, if there is one, the
    refaced image next to it; `template_part` is 1 where the refaced image was filled from the
    template, and is drawn in turbo. Each of `extras`, as (name, defaced image), gets a GIF of
    its own. Images may have different grids. 4D images show their first volume.
    """
    panels = [_Panel("defaced", defaced)]
    if refaced is not None:
        panels.append(_Panel("refaced", refaced, template_part))
    sections = [_Section(title, panels)]
    sections += [_Section(name, [_Panel("defaced", image)]) for name, image in extras]
    body = []
    for section in sections:
        gif, width = _sweep_gif(section.panels)
        titles = "".join(f"<span>{escape(p.title)}</span>" for p in section.panels)
        body.append(
            f"<section><h2>{escape(section.name)}</h2>"
            f'<div class="figure" style="max-width:{width}px">'
            f'<div class="titles" style="grid-template-columns:repeat({len(section.panels)},1fr)">'
            f'{titles}</div><img alt="Sagittal sweep of {escape(section.name)}" '
            f'src="data:image/gif;base64,{gif}"></div></section>'
        )
    path.write_text(encoding="utf-8", data=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>FaceOff QC</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#222; --muted:#666; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16161a; --fg:#e6e6e6; --muted:#9a9a9a; }} }}
body {{ margin:0 auto; max-width:900px; padding:16px; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; }}
h1 {{ font-size:1.4rem }} h2 {{ font-size:1.1rem; margin-top:2rem }}
p {{ color:var(--muted) }}
.figure {{ width:100% }}
.titles {{ display:grid; font-size:.7rem; margin-bottom:4px; text-align:center }}
.titles span {{ min-width:0; overflow-wrap:anywhere }}
.figure img {{ display:block; width:100%; border-radius:6px }}
</style></head><body>
<h1>FaceOff QC: {escape(title)}</h1>
<p>Each animation sweeps through the sagittal slices of the head at {FPS} frames per second. Where a refaced image is shown, the part filled from the template is in turbo.</p>
{"".join(body)}
</body></html>
""")
