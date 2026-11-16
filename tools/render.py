"""Headless software renderer for CustomSlop icons (no GPU, no game client, no Steam).

Renders a compiled Source model (LOD0 from MDL/VVD/VTX) with its base textures, in the style
of TF2 Classified's loadout icons (materials/vgui/loadout/weapons/*.vtf): transparent
background, three-quarter side view with the muzzle pointing left, soft key + fill + rim light,
the weapon filling a wide band through the middle of a 512x512 square (the armory and weapon
selection HUD show the centre of the square texture).

usage: python -I render.py <model.mdl> <out.png> --texroot <dir with materials/> [--texroot ...]
             [--yaw 25] [--pitch 12] [--size 512] [--ss 2]
"""
import argparse
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srcmodel as S  # noqa: E402
import vtf  # noqa: E402


def find_material(model, tex, roots):
    """Resolve texture name through cdmaterials -> (vmt path, basetexture image or None)."""
    for cd in model.cdmaterials:
        for r in roots:
            p = os.path.join(r, "materials", re.sub("/+", "/", (cd + tex).replace(chr(92), "/")).lstrip("/") + ".vmt")
            if os.path.exists(p):
                t = open(p, encoding="latin-1").read()
                mm = re.search(r'"\$basetexture"\s+"([^"]+)"', t, re.I)
                if not mm:
                    return p, None
                bt = mm.group(1).replace("\\", "/")
                for r2 in roots:
                    q = os.path.join(r2, "materials", bt + ".vtf")
                    if os.path.exists(q):
                        return p, vtf.decode(open(q, "rb").read())[2]
                return p, None
    return None, None


def rot(yaw, pitch):
    y, p = np.radians(yaw), np.radians(pitch)
    Rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(p), 0, np.sin(p)], [0, 1, 0], [-np.sin(p), 0, np.cos(p)]])
    return Ry @ Rz


def render(model, roots, size=512, ss=2, yaw=25.0, pitch=12.0, band=(0.92, 0.62), bodygroups=None,
           muzzle_left=True, axis=None, textures=None, mats=None, v2=False):
    """v2=True: Source-like shading (srcshade, materials from mats) + premultiplied box downsample."""
    m = model
    P = m.raw_pos.copy()
    N = m.raw_nrm.copy()
    # weapon frame: put the muzzle axis on screen-left
    W = S.rest_world(m)
    mz = [a for a in m.attachments if a["name"].lower() == "muzzle"]
    if axis is None:
        axis = (W[mz[0]["bone"]] @ mz[0]["local"])[:3, 3] if mz else np.linalg.svd(P - P.mean(0))[2][0]
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    # build a basis: x' = -axis (muzzle to the left in screen space), z' = up-ish
    xs = -axis if muzzle_left else axis
    # view along the model's thinnest direction (3rd principal component), so flat parts such as
    # axe heads and blades face the camera instead of being seen edge-on; "up" keeps world-z sign
    Pc = P - P.mean(0)
    pcs = np.linalg.svd(Pc, full_matrices=False)[2]
    thin = pcs[2] - xs * (pcs[2] @ xs)
    if np.linalg.norm(thin) < 1e-6:
        thin = np.cross(xs, [0, 0, 1.0])
    ys = thin / np.linalg.norm(thin)
    zs = np.cross(xs, ys)
    if zs[2] < 0:
        zs, ys = -zs, -ys
    B = np.stack([xs, ys, zs])           # rows: screen-right, depth, screen-up
    R = rot(yaw, pitch)
    M = R @ B
    Q = P @ M.T
    NN = N @ M.T
    # choose tris: bodypart model 0 of every bodypart (default bodygroups)
    tris = []
    first_model = {}
    for bpi, bp in enumerate(m.bodyparts):
        md = bp["models"][(bodygroups or {}).get(bpi, 0)]
        lo, hi = md["vstart"], md["vstart"] + md["nverts"]
        first_model[bpi] = (lo, hi)
    keep = []
    for mat, t in m.tris:
        sel = np.zeros(len(t), bool)
        for lo, hi in first_model.values():
            sel |= (t[:, 0] >= lo) & (t[:, 0] < hi)
        if sel.any():
            keep.append((mat, t[sel]))
    used = np.unique(np.concatenate([t.ravel() for _, t in keep]))
    lo, hi = Q[used].min(0), Q[used].max(0)
    S_ = size * ss
    span_x, span_z = hi[0] - lo[0], hi[2] - lo[2]
    scale = min(band[0] * S_ / span_x, band[1] * S_ / span_z)
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    sx = (Q[:, 0] - cx) * scale + S_ / 2
    sy = S_ / 2 - (Q[:, 2] - cz) * scale
    depth = Q[:, 1]                      # larger = farther
    zbuf = np.full((S_, S_), np.inf)
    col = np.zeros((S_, S_, 3))
    alpha = np.zeros((S_, S_))
    nb = np.zeros((S_, S_, 3), np.float32)
    ab = np.zeros((S_, S_, 3), np.float32)
    bab = np.ones((S_, S_), np.float32)
    uvb = np.zeros((S_, S_, 2), np.float32)
    mb = np.full((S_, S_), -1, np.int32)
    texs = {}
    for k, tname in enumerate(m.textures):
        texs[k] = textures.get(k) if textures is not None else find_material(m, tname, roots)[1]
    skin0 = m.skins[0] if m.skins else list(range(len(m.textures)))
    L1 = np.array([-0.45, -0.75, 0.55]); L1 /= np.linalg.norm(L1)     # key: front-left-top
    L2 = np.array([0.6, -0.3, -0.2]); L2 /= np.linalg.norm(L2)       # fill
    V = np.array([0, -1.0, 0])                                         # toward camera
    for mat, t in keep:
        tex = texs.get(skin0[mat] if mat < len(skin0) else mat)
        th, tw = (tex.shape[0], tex.shape[1]) if tex is not None else (1, 1)
        for a, b_, c in t:
            xa, xb, xc = sx[[a, b_, c]]
            ya, yb, yc = sy[[a, b_, c]]
            x0, x1 = int(max(0, np.floor(min(xa, xb, xc)))), int(min(S_ - 1, np.ceil(max(xa, xb, xc))))
            y0, y1 = int(max(0, np.floor(min(ya, yb, yc)))), int(min(S_ - 1, np.ceil(max(ya, yb, yc))))
            if x1 < x0 or y1 < y0:
                continue
            den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
            if abs(den) < 1e-12:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((yb - yc) * (gx - xc) + (xc - xb) * (gy - yc)) / den
            w1 = ((yc - ya) * (gx - xc) + (xa - xc) * (gy - yc)) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            z = w0 * depth[a] + w1 * depth[b_] + w2 * depth[c]
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            win = inside & (z < zb)
            if not win.any():
                continue
            zb[win] = z[win]
            n = (w0[..., None] * NN[a] + w1[..., None] * NN[b_] + w2[..., None] * NN[c])[win]
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
            uv = (w0[..., None] * m.raw_uv[a] + w1[..., None] * m.raw_uv[b_] + w2[..., None] * m.raw_uv[c])[win]
            ti_ = skin0[mat] if mat < len(skin0) else mat
            if tex is not None:
                tu = (np.mod(uv[:, 0], 1.0) * tw).astype(int).clip(0, tw - 1)
                tv = (np.mod(uv[:, 1], 1.0) * th).astype(int).clip(0, th - 1)
                albedo = tex[tv, tu, :3] / 255.0
                if tex.shape[2] > 3:
                    bab[y0:y1 + 1, x0:x1 + 1][win] = tex[tv, tu, 3] / 255.0
            else:
                albedo = np.full((win.sum(), 3), 0.6)
            nb[y0:y1 + 1, x0:x1 + 1][win] = n
            ab[y0:y1 + 1, x0:x1 + 1][win] = albedo
            uvb[y0:y1 + 1, x0:x1 + 1][win] = uv
            mb[y0:y1 + 1, x0:x1 + 1][win] = ti_
            ndl1 = np.clip(n @ L1, 0, 1)
            ndl2 = np.clip(n @ L2, 0, 1)
            hl = (n @ L1) * 0.5 + 0.5                      # half-lambert like TF2 shading
            h1 = L1 + V; h1 /= np.linalg.norm(h1)
            spec = np.clip(n @ h1, 0, 1) ** 24 * 0.35
            rim = (1 - np.clip(n @ V * -1, 0, 1)) ** 4 * 0.25
            shade = 0.28 + 0.62 * hl ** 2 + 0.2 * ndl1 + 0.12 * ndl2
            c_ = albedo * shade[:, None] + (spec + rim)[:, None]
            cb = col[y0:y1 + 1, x0:x1 + 1]
            cb[win] = np.clip(c_, 0, 1)
            alpha[y0:y1 + 1, x0:x1 + 1][win] = 1.0
    if v2:
        import srcshade as SS
        c2 = SS.shade(nb, ab, bab, uvb, mb, alpha, mats)
        return Image.fromarray(SS.downsample_premul(c2, alpha, ss), "RGBA")
    img = np.dstack([col * 255, alpha * 255]).astype(np.uint8)
    im = Image.fromarray(img, "RGBA")
    if ss > 1:
        # premultiplied downsample keeps edges clean on transparent background
        pre = np.dstack([col * alpha[..., None], alpha])
        pim = Image.fromarray((pre * 255).astype(np.uint8), "RGBA").resize((size, size), Image.LANCZOS)
        a = np.asarray(pim).astype(np.float32) / 255.0
        rgb = a[..., :3] / np.maximum(a[..., 3:4], 1e-4)
        im = Image.fromarray(np.dstack([np.clip(rgb, 0, 1) * 255, a[..., 3] * 255]).astype(np.uint8), "RGBA")
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mdl")
    ap.add_argument("out")
    ap.add_argument("--texroot", action="append", required=True)
    ap.add_argument("--yaw", type=float, default=25)
    ap.add_argument("--pitch", type=float, default=12)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--ss", type=int, default=2)
    a = ap.parse_args()
    im = render(S.load(a.mdl), a.texroot, size=a.size, ss=a.ss, yaw=a.yaw, pitch=a.pitch)
    im.save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
