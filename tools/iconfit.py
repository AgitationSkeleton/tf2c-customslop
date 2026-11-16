"""Fit CustomSlop's icon camera + lighting to each donor's own stock icon, then render mutated
weapons with the fitted style so they look like the stock icons (only shape and colour differ).

Per donor (world model, else view model) with a stock icon (image_inventory[_large] VTF):
  1. pose: yaw/pitch/roll searched coarse-to-fine; each candidate is rasterised once (orthographic)
     and its silhouette compared with the icon's alpha after aligning both bounding boxes
     (score = IoU at 96 px); mirrored poses included
  2. framing: the icon's alpha bbox in its 512 canvas + the model-units-to-pixels scale
  3. lighting: with the pose fixed, normals/albedo buffers are kept and a key+fill+rim+ambient,
     gamma/contrast shading model is fitted to the icon's luminance inside the silhouette
     (score = SSIM-like structural similarity, random search)
Stored per donor: cache/icon_fit/<src>_<id>.json (versioned). Donors without a stock icon use
the mean fitted style of their weapon family (cache/icon_fit/_family_<fam>.json).

render_icon(model, textures, fit, size=512, ref_model=None) -> PIL RGBA
"""
import json
import math
import os

import numpy as np
from PIL import Image

import srcmodel as S

VERSION = 1
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "icon_fit")


def rot(yaw, pitch, roll):
    y, p, r = np.radians([yaw, pitch, roll])
    Rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(p), 0, np.sin(p)], [0, 1, 0], [-np.sin(p), 0, np.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(r), -np.sin(r)], [0, np.sin(r), np.cos(r)]])
    return Rx @ Ry @ Rz


def tri_list(m):
    """LOD0 triangles of the DEFAULT bodygroups only (model 0 of every bodypart), with skin-0 textures."""
    ranges = [(bp["models"][0]["vstart"], bp["models"][0]["vstart"] + bp["models"][0]["nverts"]) for bp in m.bodyparts]
    out = []
    for mat, t in m.tris:
        sel = np.zeros(len(t), bool)
        for lo, hi in ranges:
            sel |= (t[:, 0] >= lo) & (t[:, 0] < hi)
        t = t[sel]
        if not len(t):
            continue
        ti = m.skins[0][mat] if m.skins and mat < len(m.skins[0]) else mat
        out.append((ti, t))
    return out


def raster_buffers(m, R, size, scale=None, centre=None, textures=None, mirror=False):
    """Orthographic raster: screen x = (R p).x, up = (R p).z, depth = (R p).y. Returns alpha,
    normal (view space), albedo buffers and the scale/centre used (units -> px)."""
    P = m.raw_pos @ R.T
    N = m.raw_nrm @ R.T
    if mirror:
        P[:, 0] *= -1
        N[:, 0] *= -1
    tl = tri_list(m)
    used = np.unique(np.concatenate([t.ravel() for _, t in tl]))
    lo, hi = P[used].min(0), P[used].max(0)
    if scale is None:
        scale = 0.9 * size / max(hi[0] - lo[0], hi[2] - lo[2], 1e-3)
    if centre is None:
        centre = ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)
    sx = (P[:, 0] - centre[0]) * scale + size / 2
    sy = size / 2 - (P[:, 2] - centre[1]) * scale
    dep = P[:, 1]
    z = np.full((size, size), np.inf)
    alpha = np.zeros((size, size), np.float32)
    nrm = np.zeros((size, size, 3), np.float32)
    alb = np.full((size, size, 3), 0.6, np.float32)
    uv = m.raw_uv
    for ti, T in tl:
        tex = (textures or {}).get(ti)
        th, tw = (tex.shape[0], tex.shape[1]) if tex is not None else (1, 1)
        for a, b, c in T:
            xa, xb, xc = sx[a], sx[b], sx[c]
            ya, yb, yc = sy[a], sy[b], sy[c]
            x0, x1 = int(max(0, math.floor(min(xa, xb, xc)))), int(min(size - 1, math.ceil(max(xa, xb, xc))))
            y0, y1 = int(max(0, math.floor(min(ya, yb, yc)))), int(min(size - 1, math.ceil(max(ya, yb, yc))))
            if x1 < x0 or y1 < y0:
                continue
            den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
            if abs(den) < 1e-12:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
            w0 = ((yb - yc) * (gx - xc) + (xc - xb) * (gy - yc)) / den
            w1 = ((yc - ya) * (gx - xc) + (xa - xc) * (gy - yc)) / den
            w2 = 1 - w0 - w1
            ins = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not ins.any():
                continue
            zz = w0 * dep[a] + w1 * dep[b] + w2 * dep[c]
            zb = z[y0:y1 + 1, x0:x1 + 1]
            win = ins & (zz < zb)
            if not win.any():
                continue
            zb[win] = zz[win]
            n = (w0[..., None] * N[a] + w1[..., None] * N[b] + w2[..., None] * N[c])[win]
            nrm[y0:y1 + 1, x0:x1 + 1][win] = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)
            alpha[y0:y1 + 1, x0:x1 + 1][win] = 1
            if tex is not None:
                u = (w0[..., None] * uv[a] + w1[..., None] * uv[b] + w2[..., None] * uv[c])[win]
                alb[y0:y1 + 1, x0:x1 + 1][win] = tex[(np.mod(u[:, 1], 1) * th).astype(int).clip(0, th - 1),
                                                     (np.mod(u[:, 0], 1) * tw).astype(int).clip(0, tw - 1), :3] / 255.0
    return dict(alpha=alpha, nrm=nrm, alb=alb, scale=scale, centre=centre)


DEFAULT_LIGHT = dict(az=-120.0, el=40.0, key=0.75, fill=0.25, rim=0.25, amb=0.30, spec=0.25, gamma=1.0, contrast=1.0)


def shade(buf, L):
    n, alb = buf["nrm"], buf["alb"]
    az, el = math.radians(L["az"]), math.radians(L["el"])
    # view space: +x right, +y away from camera, +z up; light vector toward the light
    k = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    f = np.array([-k[0], k[1], -k[2] * 0.3])
    f /= np.linalg.norm(f) + 1e-9
    v = np.array([0, -1.0, 0])
    nk = np.clip(n @ k, 0, 1)
    nf = np.clip(n @ f, 0, 1)
    rim = (1 - np.clip(n @ v * 1.0, 0, 1)) ** 3
    h = k + v
    h /= np.linalg.norm(h)
    spec = np.clip(n @ h, 0, 1) ** 20
    lum = L["amb"] + L["key"] * nk + L["fill"] * nf
    col = alb * lum[..., None] + (L["spec"] * spec + L["rim"] * rim)[..., None]
    col = np.clip(col, 0, 1) ** (1.0 / max(0.3, L["gamma"]))
    col = np.clip((col - 0.5) * L["contrast"] + 0.5, 0, 1)
    return col


def bbox(mask):
    ys, xs = np.nonzero(mask > 0.5)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def crop_norm(img, bb, n=96):
    x0, y0, x1, y1 = bb
    c = img[y0:y1, x0:x1]
    return np.asarray(Image.fromarray((c * 255).astype(np.uint8)).resize((n, n), Image.BILINEAR)).astype(np.float32) / 255


def iou(a, b):
    a, b = a > 0.5, b > 0.5
    return float((a & b).sum() / max(1, (a | b).sum()))


def ssim(x, y):
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(), y.var()
    cxy = ((x - mx) * (y - my)).mean()
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    return float((2 * mx * my + c1) * (2 * cxy + c2) / ((mx * mx + my * my + c1) * (vx + vy + c2)))


def fit(m, textures, icon_rgba, rng, coarse=True):
    """-> fitted dict (pose, framing, light, scores)."""
    ia = icon_rgba[..., 3].astype(np.float32) / 255
    ibb = bbox(ia)
    if ibb is None:
        return None
    imask = crop_norm(ia, ibb)
    best = (-1, None)
    S_ = 128

    def score_pose(yaw, pitch, roll, mirror):
        buf = raster_buffers(m, rot(yaw, pitch, roll), S_, mirror=mirror)
        bb = bbox(buf["alpha"])
        if bb is None:
            return -1
        # aspect of the bbox matters too: compare un-normalised aspect ratio
        ar_i = (ibb[2] - ibb[0]) / max(1, ibb[3] - ibb[1])
        ar_r = (bb[2] - bb[0]) / max(1, bb[3] - bb[1])
        return iou(crop_norm(buf["alpha"], bb), imask) - 0.25 * abs(math.log(ar_i / max(1e-3, ar_r)))
    cands = []
    for yaw in range(0, 360, 30):
        for pitch in (-40, -20, 0, 20, 40):
            for roll in (0, 180):
                for mir in (False,):
                    cands.append((yaw, pitch, roll, mir))
    scored = sorted(((score_pose(*c_), c_) for c_ in cands), key=lambda x: -x[0])
    # silhouettes are ambiguous (a gun seen from its left or right side has nearly the same outline):
    # re-rank the best silhouettes by textured luminance correlation with the icon (default light)
    il_small = crop_norm((icon_rgba[..., :3].astype(np.float32) / 255).mean(-1), ibb)
    ranked = []
    for s_, c_ in scored[:8]:
        buf = raster_buffers(m, rot(*c_[:3]), S_, textures=textures, mirror=c_[3])
        bb = bbox(buf["alpha"])
        lum = crop_norm(shade(buf, DEFAULT_LIGHT).mean(-1), bb)
        msk = (crop_norm(buf["alpha"], bb) > 0.5) & (imask > 0.5)
        corr = float(np.corrcoef(lum[msk], il_small[msk])[0, 1]) if msk.sum() > 30 else 0.0
        ranked.append((0.6 * s_ + 0.4 * corr, c_, s_))
    ranked.sort(key=lambda x: -x[0])
    best = (ranked[0][2], ranked[0][1])
    # local refinement (silhouette), starting from the re-ranked pose
    cur = list(best[1])
    step = [15.0, 10.0, 15.0]
    for it in range(36):
        k = it % 3
        trial = list(cur)
        trial[k] += rng.choice([-1, 1]) * step[k]
        s = score_pose(*trial)
        if s > best[0]:
            best, cur = (s, tuple(trial)), trial
        if it % 9 == 8:
            step = [x * 0.6 for x in step]
    yaw, pitch, roll, mir = best[1]
    # framing at full size: units -> px so the donor's bbox matches the icon's bbox
    R = rot(yaw, pitch, roll)
    buf0 = raster_buffers(m, R, 512, mirror=mir)
    bb0 = bbox(buf0["alpha"])
    sfac = min((ibb[2] - ibb[0]) / max(1, bb0[2] - bb0[0]), (ibb[3] - ibb[1]) / max(1, bb0[3] - bb0[1]))
    scale = buf0["scale"] * sfac
    # centre: model-space screen centre that maps to the icon bbox centre
    P = m.raw_pos @ R.T
    if mir:
        P[:, 0] *= -1
    lo, hi = P.min(0), P.max(0)
    mc = ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)
    icx, icy = (ibb[0] + ibb[2]) / 2, (ibb[1] + ibb[3]) / 2
    centre = (mc[0] - (icx - 256) / scale, mc[1] + (icy - 256) / scale)
    buf = raster_buffers(m, R, 512, scale=scale, centre=centre, textures=textures, mirror=mir)
    # lighting: random search on the luminance inside the shared silhouette
    il = (icon_rgba[..., :3].astype(np.float32) / 255).mean(-1)
    both = (buf["alpha"] > 0.5) & (ia > 0.5)
    L = dict(DEFAULT_LIGHT)

    def lscore(L_):
        col = shade(buf, L_).mean(-1)
        if both.sum() < 50:
            return -1
        return ssim(col[both], il[both]) - abs(float(col[both].mean() - il[both].mean()))
    bestl = (lscore(L), dict(L))
    for it in range(220):
        T_ = dict(bestl[1])
        for key, sd, lo_, hi_ in (("az", 40, -180, 180), ("el", 15, -10, 85), ("key", .15, 0, 1.5), ("fill", .1, 0, 1),
                                 ("rim", .1, 0, .8), ("amb", .08, 0, .8), ("spec", .08, 0, .8), ("gamma", .1, .6, 1.8),
                                 ("contrast", .1, .6, 1.6)):
            if rng.random() < 0.4:
                T_[key] = float(np.clip(T_[key] + rng.gauss(0, sd) * (1 - it / 260), lo_, hi_))
        s = lscore(T_)
        if s > bestl[0]:
            bestl = (s, T_)
    final_iou = iou(buf["alpha"], ia)
    return dict(version=VERSION, yaw=yaw, pitch=pitch, roll=roll, mirror=mir, scale=scale, centre=list(centre),
                icon_bbox=list(map(int, ibb)), light=bestl[1], scores=dict(pose_iou_bbox=round(best[0], 3),
                                                                           iou_canvas=round(final_iou, 3),
                                                                           light_ssim=round(bestl[0], 3)))


def render_icon(m, textures, f, size=512, ss=2):
    """Render with a fitted style. The donor's scale/centre are reused so a longer mutated barrel
    really looks longer; if the mutated model would leave the canvas it is shrunk to fit."""
    R = np.array(f["R"]) if "R" in f else rot(f["yaw"], f["pitch"], f["roll"])
    S2 = size * ss
    scale = f["scale"] * ss if f.get("scale") else None
    centre = tuple(f["centre"]) if f.get("centre") else None
    buf = raster_buffers(m, R, S2, scale=scale, centre=centre, textures=textures, mirror=f["mirror"])
    bb = bbox(buf["alpha"])
    if scale is not None and (bb is None or bb[0] <= 1 or bb[1] <= 1 or bb[2] >= S2 - 1 or bb[3] >= S2 - 1):
        buf = raster_buffers(m, R, S2, scale=None, centre=None, textures=textures, mirror=f["mirror"])
    col = shade(buf, f["light"])
    a = buf["alpha"]
    pre = np.dstack([col * a[..., None], a])
    pim = Image.fromarray((pre * 255).astype(np.uint8), "RGBA").resize((size, size), Image.LANCZOS)
    q = np.asarray(pim).astype(np.float32) / 255
    rgb = q[..., :3] / np.maximum(q[..., 3:4], 1e-4)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 1) * 255, q[..., 3] * 255]).astype(np.uint8), "RGBA")


def cache_path(key):
    return os.path.join(CACHE, "%s_v%d.json" % (key.replace(":", "_"), VERSION))


def family_style(fam):
    p = os.path.join(CACHE, "_family_%s.json" % fam)
    return json.load(open(p)) if os.path.exists(p) else None


def default_style(m, light=None):
    """No stock icon: three-quarter side view along the thinnest axis (as render.py), autoscaled,
    with the given (family mean) lighting."""
    P = m.raw_pos - m.raw_pos.mean(0)
    pcs = np.linalg.svd(P, full_matrices=False)[2]
    xs = pcs[0]
    W = S.rest_world(m)
    mz = [a for a in m.attachments if a["name"].lower() == "muzzle"]
    if mz and ((W[mz[0]["bone"]] @ mz[0]["local"])[:3, 3] - m.raw_pos.mean(0)) @ xs > 0:
        xs = -xs
    ys = pcs[2] - xs * (pcs[2] @ xs)
    ys /= np.linalg.norm(ys)
    zs = np.cross(xs, ys)
    if zs[2] < 0:
        zs, ys = -zs, -ys
    B = np.stack([xs, ys, zs])
    tilt = rot(25, 12, 0)
    return dict(R=(tilt @ B).tolist(), mirror=False, scale=None, centre=None, light=light or dict(DEFAULT_LIGHT))
