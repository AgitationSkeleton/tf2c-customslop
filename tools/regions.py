"""Colour regions for a donor model, mapped back to texture (UV) space. Cached + versioned.

Regions per vertex (v3, 2026-11-21: more zones so one-piece weapons are not one flat colour):
  grip    vertices the hand-rig protection keeps still (weight < 0.5) - the handle / held area
  accent  small connected parts (< 3% of the vertices: sights, screws, rings, triggers)
  front   the front of the weapon along its long axis (barrel, blade, head)
  rear    the back of the weapon (stock, butt, pommel)
  body    everything else (receiver, drum, ...)
Parts of 3-25% of the mesh are labelled whole by their centroid; bigger parts (one-piece models)
are split per vertex along the axis, so a single mesh still gets front / body / rear.
For each texture the model uses, every region gets a UV mask (its triangles rasterised in UV
space, grown 2 texels) plus a per-texel "station" map t (0 = back, 1 = muzzle/tip) for gradients.
Cache: cache/regions/<sha1(model bytes)>_v<VERSION>.npz
"""
import hashlib
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import mutate as MU

VERSION = 3
NAMES = ["grip", "accent", "front", "body", "rear"]
DEBUG_COL = {"grip": (230, 60, 60), "accent": (250, 210, 40), "front": (60, 140, 240), "body": (90, 200, 110),
             "rear": (200, 90, 220)}
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
        elif sel.sum() > 0.25 * m.nraw:            # big / only part: split along the axis
            lab[sel & (tn > 0.62)] = 2             # front
            lab[sel & (tn < 0.30)] = 4             # rear
        elif tn[sel].mean() > 0.55:
            lab[sel] = 2                           # front
        elif tn[sel].mean() < 0.30:
            lab[sel] = 4                           # rear
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
            r = int(np.bincount(lab[tri], minlength=len(NAMES)).argmax())
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


# ------------------------------------------------------------------ UV islands (palette v4)
ISLAND_VERSION = 2


def uv_islands(m):
    """Island id per raw vertex: triangles sharing a vertex index (UV seams split vertices, so this
    is UV connectivity). A whole island is painted as one unit - no speckle, no strips."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    rows, cols = [], []
    for _, T in m.tris:
        T = np.asarray(T)
        if len(T):
            rows += [T[:, 0], T[:, 1]]
            cols += [T[:, 1], T[:, 2]]
    r, c = np.concatenate(rows), np.concatenate(cols)
    g = sp.coo_matrix((np.ones(len(r), np.int8), (r, c)), shape=(m.nraw, m.nraw))
    return connected_components(g, directed=False)[1]


def _dilate_ids(a, n=2):
    """Grow non-zero ids into zero texels (gutters) so DXT blocks / filtering show no seams."""
    for _ in range(n):
        z = a == 0
        if not z.any():
            break
        b = a.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s = np.roll(np.roll(a, dy, 0), dx, 1)
            take = z & (b == 0) & (s > 0)
            b[take] = s[take]
        a = b
    return a


def island_map(model_path, m, tex_sizes):
    """-> ({texture index: int32 HxW island id + 1 (0 = unused)}, info) with info arrays per island:
    station (0 back .. 1 muzzle), region label (NAMES index, majority), vertex share."""
    key = hashlib.sha1(open(model_path, "rb").read() + repr(sorted(tex_sizes.items())).encode()).hexdigest()[:16]
    cp = os.path.join(ROOT, "cache", "regions", "%s_isl%d_v%d.npz" % (key, ISLAND_VERSION, VERSION))
    if os.path.exists(cp):
        z = np.load(cp)
        return {int(k[1:]): z[k] for k in z.files if k.startswith("m")}, \
            dict(station=z["station"], label=z["label"], share=z["share"])
    lab, tn = vertex_regions(m)
    isl = uv_islands(m)
    n = int(isl.max()) + 1
    cnt = np.bincount(isl, minlength=n).astype(np.float64)
    station = np.bincount(isl, weights=tn, minlength=n) / np.maximum(cnt, 1)
    label = np.array([np.bincount(lab[isl == i], minlength=len(NAMES)).argmax() if cnt[i] else 3 for i in range(n)])
    share = cnt / max(1, cnt.sum())
    uv = m.raw_uv
    # islands that overlap in texture space (mirrored / stacked UVs share texels) are merged, so a
    # texel never gets two paints (the patchwork on the Minelayer)
    per_tex = {}
    for mat, T in m.tris:
        ti = m.skins[0][mat] if m.skins and mat < len(m.skins[0]) else mat
        if ti in tex_sizes:
            for tri in T:
                per_tex.setdefault(ti, {}).setdefault(int(isl[tri[0]]), []).append(tri)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for ti, groups in per_tex.items():
        w, h = tex_sizes[ti]
        owner = np.zeros((h, w), np.int32)
        for i, tris in groups.items():
            im = Image.new("L", (w, h), 0)
            dr = ImageDraw.Draw(im)
            for tri in tris:
                dr.polygon([(float(uv[k, 0] % 1.0) * w, float(uv[k, 1] % 1.0) * h) for k in tri], fill=255)
            mk = np.asarray(im) > 0
            area = int(mk.sum())
            if area:
                hit = owner[mk]
                hit = hit[hit > 0]
                if hit.size:
                    ids_, cn = np.unique(hit, return_counts=True)
                    for o, c_ in zip(ids_, cn):
                        if c_ > 0.15 * area or c_ > 0.15 * float((owner == o).sum()):
                            parent[find(i)] = find(int(o) - 1)
                owner[mk & (owner == 0)] = i + 1
    root = np.array([find(i) for i in range(n)])
    maps = {}
    for ti, groups in per_tex.items():
        w, h = tex_sizes[ti]
        im = Image.new("I", (w, h), 0)
        dr = ImageDraw.Draw(im)
        for i, tris in groups.items():
            for tri in tris:
                dr.polygon([(float(uv[k, 0] % 1.0) * w, float(uv[k, 1] % 1.0) * h) for k in tri], fill=int(root[i]) + 1)
        maps[ti] = _dilate_ids(np.asarray(im, np.int32))
    # merged islands: station / share / label of the union
    for r_ in np.unique(root):
        mem = np.nonzero(root == r_)[0]
        if len(mem) > 1:
            wsum = share[mem].sum()
            station[r_] = float((station[mem] * share[mem]).sum() / max(wsum, 1e-9))
            label[r_] = label[mem[np.argmax(share[mem])]]
            share[r_] = wsum
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    np.savez_compressed(cp, station=station, label=label, share=share, **{"m%d" % k: v for k, v in maps.items()})
    return maps, dict(station=station, label=label, share=share)
