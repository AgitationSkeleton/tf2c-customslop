"""CustomSlop texture recolouring prototype.

Two modes on a VTF basetexture (DXT1/DXT5/uncompressed):
  * global HSV transform (hue shift, saturation and value multipliers, optional tint) on the
    decoded image, re-encoded as DXT (Pillow's DDS writer) with a full mip chain;
  * section recolour: a mask rasterised in UV space from the triangles of a model region
    (e.g. the stretched barrel: vertices past a station along the muzzle axis), so only the
    texels that region uses change colour.
VMTs are copied with $basetexture repointed; every other texture ($bumpmap, phong exponent,
lightwarp) keeps its stock path, so clients download only the new base texture.

usage (library): see build_proto.py
"""
import colorsys
import os
import re

import numpy as np
from PIL import Image, ImageDraw

import vtf


def hsv_transform(rgb, hue_deg=0.0, sat=1.0, val=1.0, tint=None, tint_amt=0.0):
    """rgb float array (...,3) in 0..1 -> transformed. Vectorised HSV."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rr = m & (mx == r)
    gg = m & (mx == g) & ~rr
    bb = m & ~rr & ~gg
    h[rr] = ((g - b)[rr] / d[rr]) % 6
    h[gg] = (b - r)[gg] / d[gg] + 2
    h[bb] = (r - g)[bb] / d[bb] + 4
    h = (h / 6.0 + hue_deg / 360.0) % 1.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0) * sat
    v = mx * val
    s, v = np.clip(s, 0, 1), np.clip(v, 0, 1)
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]),
                    np.choose(i, [p, p, t, v, v, q])], -1)
    if tint is not None and tint_amt > 0:
        lum = (0.299 * out[..., 0] + 0.587 * out[..., 1] + 0.114 * out[..., 2])[..., None]
        out = out * (1 - tint_amt) + lum * np.array(tint) * tint_amt * 1.6
    return np.clip(out, 0, 1)


def uv_mask(model, tri_sel, size):
    """Rasterise the UV triangles (rows of VVD indices) into a size x size mask (0..255)."""
    w, h = size
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    uv = model.raw_uv
    for tri in tri_sel:
        pts = [(float(uv[k, 0] % 1.0) * w, float(uv[k, 1] % 1.0) * h) for k in tri]
        dr.polygon(pts, fill=255)
    # grow by a few texels so DXT blocks and bilinear filtering do not leave seams
    from PIL import ImageFilter
    im = im.filter(ImageFilter.MaxFilter(5))
    return np.asarray(im).astype(np.float32) / 255.0


def recolor_vtf(src_vtf, dst_vtf, global_op=None, section=None):
    """global_op / section: dicts for hsv_transform (+ 'mask' array for section)."""
    data = open(src_vtf, "rb").read()
    w, h, img, info = vtf.decode(data)
    rgb = img[..., :3].astype(np.float32) / 255.0
    out = rgb
    if global_op:
        out = hsv_transform(out, **global_op)
    if section:
        op = dict(section)
        mask = op.pop("mask")[..., None]
        out = out * (1 - mask) + hsv_transform(out, **op) * mask
    res = np.dstack([(out * 255 + 0.5).astype(np.uint8), img[..., 3]])
    fmt = info["fmt"] if info["fmt"] in (13, 15) else 15
    os.makedirs(os.path.dirname(dst_vtf), exist_ok=True)
    open(dst_vtf, "wb").write(vtf.encode(res, fmt=fmt, mips=info["mips"] > 1, flags=info["flags"]))
    return res


def write_vmt(src_vmt, dst_vmt, new_base):
    t = open(src_vmt, encoding="latin-1").read()
    t2, n = re.subn(r'("\$basetexture"\s+)"[^"]*"', lambda mm: mm.group(1) + '"%s"' % new_base, t,
                    flags=re.I)
    assert n == 1, "no $basetexture in " + src_vmt
    os.makedirs(os.path.dirname(dst_vmt), exist_ok=True)
    open(dst_vmt, "w", encoding="latin-1").write(t2)
