"""Colour regions for a donor model, mapped back to texture (UV) space. Cached + versioned.

Regions per vertex:
  grip    vertices the hand-rig protection keeps still (weight < 0.5) - the handle / held area
  accent  small connected parts (< 3% of the vertices: sights, screws, rings, triggers)
  front   parts whose centroid lies in the front 45% along the long axis (barrel, blade, head)
  body    everything else (receiver, stock, drum, ...)
For each texture the model uses, every region gets a UV mask (its triangles rasterised in UV
space, grown 2 texels) plus a per-texel "station" map t (0 = back, 1 = muzzle/tip) for gradients.
Cache: cache/regions/<sha1(model bytes)>_v<VERSION>.npz
"""
import hashlib
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import mutate as MU

VERSION = 2
NAMES = ["grip", "accent", "front", "body"]
DEBUG_COL = {"grip": (230, 60, 60), "accent": (250, 210, 40), "front": (60, 140, 240), "body": (90, 200, 110)}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def vertex_regions(m):
    P = m.raw_pos
    c = P.mean(0)
    ax = np.linalg.svd(P - c)[2][0]
    mz = [a for a in m.attachments if a["name"].lower() == "muzzle"]
    import srcmodel as S
    W = S.rest_world(m)
    ref = ((W[mz[0]["bone"]] @ mz[0]["local"])[:3, 3] - c) if mz else c
    if ax @ ref < 0:
        ax = -ax
    t = P @ ax
    tn = (t - t.min()) / max(1e-6, t.max() - t.min())
    w, _ = MU.protection(m, ax, t)
    comp = MU.components(m)
    lab = np.full(m.nraw, 3)                       # body
    for k in np.unique(comp):
        sel = comp == k
        if sel.sum() < 0.03 * m.nraw:
            lab[sel] = 1                           # accent
        elif tn[sel].mean() > 0.55:
            lab[sel] = 2                           # front
    lab[w < 0.5] = 0                               # grip wins
    return lab, tn


def uv_maps(m, tex_sizes, lab, tn):
    """-> {texture index: (masks [R,H,W] float, station HxW)} for the LOD0 triangles."""
    out = {}
    uv = m.raw_uv
    for mat, T in m.tris:
        ti = m.skins[0][mat] if m.skins and mat < len(m.skins[0]) else mat
        if ti not in tex_sizes:
            continue
        w, h = tex_sizes[ti]
        if ti not in out:
            out[ti] = ([Image.new("L", (w, h), 0) for _ in NAMES], Image.new("L", (w, h), 0))
        ims, st = out[ti]
        draws = [ImageDraw.Draw(i) for i in ims]
        ds = ImageDraw.Draw(st)
        for tri in T:
            r = int(np.bincount(lab[tri], minlength=4).argmax())
            pts = [(float(uv[k, 0] % 1.0) * w, float(uv[k, 1] % 1.0) * h) for k in tri]
            draws[r].polygon(pts, fill=255)
            ds.polygon(pts, fill=int(255 * tn[tri].mean()))
    res = {}
    for ti, (ims, st) in out.items():
        masks = np.stack([np.asarray(i.filter(ImageFilter.MaxFilter(5))).astype(np.float32) / 255 for i in ims])
        s = masks.sum(0, keepdims=True)
        masks = np.where(s > 1, masks / np.maximum(s, 1e-6), masks)
        res[ti] = (masks, np.asarray(st.filter(ImageFilter.MaxFilter(5))).astype(np.float32) / 255)
    return res


def region_map(model_path, m, tex_sizes):
    key = hashlib.sha1(open(model_path, "rb").read() + repr(sorted(tex_sizes.items())).encode()).hexdigest()[:16]
    cp = os.path.join(ROOT, "cache", "regions", "%s_v%d.npz" % (key, VERSION))
    if os.path.exists(cp):
        z = np.load(cp)
        return {int(k[1:]): (z[k], z["s" + k[1:]]) for k in z.files if k.startswith("m")}, z["lab"]
    lab, tn = vertex_regions(m)
    res = uv_maps(m, tex_sizes, lab, tn)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    np.savez_compressed(cp, lab=lab, **{"m%d" % k: v[0] for k, v in res.items()}, **{"s%d" % k: v[1] for k, v in res.items()})
    return res, lab


def debug_texture(masks):
    h, w = masks.shape[1:]
    img = np.full((h, w, 3), 40, np.float32)
    for r, nm in enumerate(NAMES):
        img = img * (1 - masks[r][..., None]) + np.array(DEBUG_COL[nm], np.float32) * masks[r][..., None]
    return np.dstack([img.astype(np.uint8), np.full((h, w), 255, np.uint8)])
