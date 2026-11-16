"""Source-engine-like shading for CustomSlop's software renders (icons, cards, previews).

Why: the first renderer shaded sRGB texels as if they were linear, with a large flat ambient and
no material response, so renders came out foggy/washed out (stock TF2C rocket launcher icon:
mean rgb 67/64/55, saturation 0.17, 39% near-black; ours: 104/105/98, 0.10, 0.1%).

Pipeline per pixel (camera space: +x right, +y away from the camera, +z up):
  albedo sRGB -> linear
  diffuse  = ambient cube (top/bottom) + sum over key/fill lights of the lighting term x:
             x = saturate(N.L) (FULL Lambert) - TF2C's own weapon materials set $phong 1 +
                 $PhongDisableHalfLambert 1 + weapon_lightwarp (TF2C LUX shaders: "$LightWarpTexture
                 remaps the computed lighting. For best results use without $HalfLambert")
             x = saturate(0.5*N.L+0.5) (half-Lambert) when $halflambert, or $phong without
                 $PhongDisableHalfLambert (forced on "for stock consistency", as TF2's materials)
             then 2*lightwarp(x) with a $lightwarptexture (Source's 2x), else x^2 (half) / x (full)
  specular = $phong: boost * mask * fresnel(ranges) * (R.V)^exponent per light
             (exponent from $phongexponenttexture R*149+1 or $phongexponent; mask from
             $basemapalphaphongmask -> base alpha, else the $bumpmap alpha)
  rim      = $rimlight: (1-N.V)^exp * boost * ambient top * rimmask
  colour   = albedo*diffuse + spec + rim (+ $selfillum)  ->  exposure  ->  linear -> sRGB
The light rig (directions, intensities, ambient, exposure) is ONE global setting calibrated
against real stock icons (tools/calibrate_render.py -> cache/icon_fit/_rig_v2.json).
"""
import json
import math
import os
import re

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIG_PATH = os.path.join(ROOT, "cache", "icon_fit", "_rig_v2.json")

# calibrated against real icons (tools/calibrate_render.py, 16 donors, 2026-11-16)
DEFAULT_RIG = dict(key_az=-85.1521, key_el=39.2724, key=1.8334, fill=0.2517, amb_top=0.2274, amb_bot=0.0,
                   rim=0.1832, spec=0.25, exposure=1.2247, warp_srgb=0.3368, warp_fallback=1.0, env=0.0097,
                   full_everywhere=0.784)


def rig():
    if os.path.exists(RIG_PATH):
        r = dict(DEFAULT_RIG)
        r.update(json.load(open(RIG_PATH)).get("rig", {}))
        return r
    return dict(DEFAULT_RIG)


def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


# ------------------------------------------------------------------ materials
def _num(txt, key, default=None):
    m = re.search(r'"?\$%s"?\s+"?\[?\s*([-0-9.eE ]+?)\s*\]?"?\s*(?:\n|$|//)' % re.escape(key), txt, re.I)
    if not m:
        return default
    vals = [float(v) for v in m.group(1).split()]
    return vals if len(vals) > 1 else vals[0]


def _str(txt, key):
    m = re.search(r'"?\$%s"?\s+"([^"]+)"' % re.escape(key), txt, re.I)
    return m.group(1).replace("\\", "/").lower() if m else None


def parse_vmt(txt, read_vtf):
    """VMT text -> material dict. read_vtf(rel 'materials/x.vtf') -> RGBA uint8 array or None."""
    if not txt:
        return {}
    mat = dict(phong=bool(_num(txt, "phong", 0)), exponent=_num(txt, "phongexponent", None),
               boost=_num(txt, "phongboost", 1.0), fresnel=_num(txt, "phongfresnelranges", [0.0, 0.5, 1.0]),
               basealphamask=bool(_num(txt, "basemapalphaphongmask", 0)),
               albedotint=bool(_num(txt, "phongalbedotint", 0)),
               rim=bool(_num(txt, "rimlight", 0)), rimexp=_num(txt, "rimlightexponent", 4.0),
               rimboost=_num(txt, "rimlightboost", 1.0), rimmask=bool(_num(txt, "rimmask", 0)),
               selfillum=bool(_num(txt, "selfillum", 0)), halflambert=bool(_num(txt, "halflambert", 0)),
               nohalf=bool(_num(txt, "phongdisablehalflambert", 0)),
               envmap=_str(txt, "envmap"), envtint=_num(txt, "envmaptint", None),
               env_basealpha=bool(_num(txt, "basealphaenvmapmask", 0)),
               env_bumpalpha=bool(_num(txt, "normalmapalphaenvmapmask", 0)))
    if not isinstance(mat["envtint"], list) or len(mat["envtint"]) != 3:
        mat["envtint"] = [1.0, 1.0, 1.0] if mat["envmap"] else None
    if not isinstance(mat["fresnel"], list) or len(mat["fresnel"]) != 3:
        mat["fresnel"] = [0.0, 0.5, 1.0]
    for key, tex in (("lightwarp", "lightwarptexture"), ("exptex", "phongexponenttexture"), ("bump", "bumpmap")):
        rel = _str(txt, tex)
        mat[key] = read_vtf("materials/" + rel + ".vtf") if rel else None
    if mat["lightwarp"] is not None:
        mat["lightwarp"] = mat["lightwarp"][0, :, :3].astype(np.float32) / 255.0      # 1D ramp (first row)
    return mat


def _sample(tex, uv):
    h, w = tex.shape[:2]
    return tex[(np.mod(uv[:, 1], 1) * h).astype(int).clip(0, h - 1), (np.mod(uv[:, 0], 1) * w).astype(int).clip(0, w - 1)]


def _warp(ramp, x, srgb):
    i = np.clip(x, 0, 1) * (len(ramp) - 1)
    lo = np.floor(i).astype(int)
    hi = np.minimum(lo + 1, len(ramp) - 1)
    t = (i - lo)[:, None]
    v = ramp[lo] * (1 - t) + ramp[hi] * t
    return srgb_to_lin(v) if srgb else v


# ------------------------------------------------------------------ shading
def shade(nrm, alb, balpha, uv, matid, mask, mats=None, R=None):
    """Buffers (HxW): nrm (3), alb sRGB 0..1 (3), balpha base-texture alpha, uv (2), matid (int),
    mask (coverage>0). mats: {matid: parse_vmt dict}. Returns sRGB colour HxWx3 (0..1)."""
    R = R or rig()
    out = np.zeros(alb.shape, np.float32)
    sel = mask > 0
    if not sel.any():
        return out
    n = nrm[sel].astype(np.float64)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    a = srgb_to_lin(alb[sel].astype(np.float64))
    ba = balpha[sel]
    uvs = uv[sel]
    mid = matid[sel]
    az, el = math.radians(R["key_az"]), math.radians(R["key_el"])
    key = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    fill = np.array([-key[0], key[1], -0.35 * key[2]])
    fill /= np.linalg.norm(fill)
    v = np.array([0.0, -1.0, 0.0])                        # toward the camera
    up = np.clip(n[:, 2] * 0.5 + 0.5, 0, 1)
    amb = R["amb_bot"] + (R["amb_top"] - R["amb_bot"]) * up
    diff = np.repeat(amb[:, None], 3, 1)
    spec = np.zeros(len(n))
    rim = np.zeros(len(n))
    nv = np.clip(n @ v, 0, 1)
    for k in np.unique(mid):
        s = mid == k
        mt = (mats or {}).get(int(k)) or {}
        lights = ((key, R["key"]), (fill, R["fill"]))
        half = (mt.get("halflambert") or (mt.get("phong") and not mt.get("nohalf")))             and R.get("full_everywhere", 0.0) < 0.5
        warp = mt.get("lightwarp")
        if warp is None and R.get("warp_fallback", 0.0) > 0.5:
            warp = mt.get("fallback_warp")
        for L, I in lights:
            nl = n[s] @ L
            x = np.clip(0.5 * nl + 0.5, 0, 1) if half else np.clip(nl, 0, 1)
            if warp is not None:
                d = 2.0 * _warp(warp, x, R.get("warp_srgb", 1.0) > 0.5)
            else:
                d = np.repeat(((x ** 2) if half else x)[:, None], 3, 1)
            diff[s] += I * d
        if mt.get("phong"):
            if mt.get("exptex") is not None:
                ex = 1.0 + 149.0 * _sample(mt["exptex"], uvs[s])[:, 0] / 255.0
            else:
                ex = np.full(s.sum(), float(mt.get("exponent") or 5.0))
            if mt.get("basealphamask"):
                pm = ba[s]
            elif mt.get("bump") is not None:
                pm = _sample(mt["bump"], uvs[s])[:, 3] / 255.0
            else:
                pm = np.ones(s.sum())
            f = 1 - nv[s]
            r0, r1, r2 = mt["fresnel"]
            fr = np.where(f < 0.5, r0 + (r1 - r0) * f * 2, r1 + (r2 - r1) * (f * 2 - 1))
            for L, I in lights:
                rv = 2 * (n[s] @ L)[:, None] * n[s] - L
                ph = np.clip(rv @ v, 0, 1) ** ex
                spec[s] += I * mt.get("boost", 1.0) * pm * fr * ph * (n[s] @ L > 0)
        if mt.get("rim"):
            rm = _sample(mt["exptex"], uvs[s])[:, 3] / 255.0 if mt.get("rimmask") and mt.get("exptex") is not None \
                else np.ones(s.sum())
            rim[s] = (1 - nv[s]) ** float(mt.get("rimexp") or 4.0) * float(mt.get("rimboost") or 1.0) * rm \
                * R["amb_top"] * (n[s][:, 2] > -0.2)
    col = a * diff + (R["spec"] * spec + R["rim"] * rim)[:, None]
    for k in np.unique(mid):                              # $envmap: tinted, masked, fresnel-ish
        mt = (mats or {}).get(int(k)) or {}
        if mt.get("envtint"):
            s = mid == k
            em = ba[s] if mt.get("env_basealpha") else (
                _sample(mt["bump"], uvs[s])[:, 3] / 255.0 if mt.get("env_bumpalpha") and mt.get("bump") is not None
                else np.ones(s.sum()))
            fr = 0.25 + 0.75 * (1 - nv[s]) ** 3
            col[s] += R.get("env", 0.15) * np.outer(em * fr * R["amb_top"] * 4, srgb_to_lin(np.array(mt["envtint"])))
    for k in np.unique(mid):
        mt = (mats or {}).get(int(k)) or {}
        if mt.get("selfillum"):
            s = mid == k
            col[s] += a[s] * ba[s][:, None]
    out[sel] = lin_to_srgb(col * R["exposure"])
    return out


# ------------------------------------------------------------------ edges / downsampling
def downsample_premul(rgb, alpha, factor):
    """Box-filter supersampled straight RGB + coverage alpha (float, premultiplied) by an integer
    factor -> straight RGBA uint8 with a crisp 1-px AA edge and no ringing / halos."""
    H, W = alpha.shape
    h, w = H // factor, W // factor
    pre = np.dstack([rgb * alpha[..., None], alpha])[:h * factor, :w * factor]
    pre = pre.reshape(h, factor, w, factor, 4).mean((1, 3))
    a = pre[..., 3]
    col = pre[..., :3] / np.maximum(a[..., None], 1e-6)
    return np.dstack([np.clip(col, 0, 1) * 255 + 0.5, a * 255 + 0.5]).astype(np.uint8)


def bleed_edges(rgba, rounds=4):
    """Fill the RGB of fully transparent pixels with the nearest edge colour so bilinear filtering /
    mips in the game don't pull black into the outline (dark fuzz)."""
    img = rgba.astype(np.float32)
    known = img[..., 3] > 0
    rgb = img[..., :3].copy()
    for _ in range(rounds):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            sh_k = np.roll(np.roll(known, dy, 0), dx, 1)
            sh_c = np.roll(np.roll(rgb, dy, 0), dx, 1)
            acc += sh_c * sh_k[..., None]
            cnt += sh_k
        new = (~known) & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        known = known | new
    out = rgba.copy()
    out[..., :3] = np.where((rgba[..., 3:4] == 0), np.clip(rgb + 0.5, 0, 255).astype(np.uint8), rgba[..., :3])
    return out


def resize_premul(rgba, size):
    """Premultiplied float resize (area filter) of straight RGBA uint8 -> straight RGBA uint8."""
    from PIL import Image
    a = rgba[..., 3:4].astype(np.float32) / 255
    pre = rgba[..., :3].astype(np.float32) / 255 * a
    chans = []
    for c in range(3):
        chans.append(np.asarray(Image.fromarray(pre[..., c]).resize(size, Image.BOX)))
    aa = np.asarray(Image.fromarray(a[..., 0]).resize(size, Image.BOX))
    rgb = np.stack(chans, -1) / np.maximum(aa[..., None], 1e-6)
    return np.dstack([np.clip(rgb, 0, 1) * 255 + 0.5, np.clip(aa, 0, 1) * 255 + 0.5]).astype(np.uint8)


# ------------------------------------------------------------------ metrics (calibration / report)
def stats(rgba):
    """Opaque-pixel stats: mean rgb, HSV saturation, near-black share (luma<40), luma histogram."""
    a = rgba[..., 3] > 127
    if a.sum() < 20:
        return None
    px = rgba[..., :3][a].astype(np.float32)
    mx, mn = px.max(1), px.min(1)
    luma = px @ np.array([0.299, 0.587, 0.114])
    hist = np.histogram(luma, bins=32, range=(0, 256))[0].astype(np.float32)
    return dict(mean=[round(float(x), 1) for x in px.mean(0)], sat=round(float(((mx - mn) / np.maximum(mx, 1)).mean()), 3),
                near_black=round(float((luma < 40).mean()), 3), luma=round(float(luma.mean()), 1),
                hist=(hist / hist.sum()).tolist())


def hist_dist(s1, s2):
    return float(np.abs(np.array(s1["hist"]) - np.array(s2["hist"])).sum() / 2)


def edge_stats(rgba, bg_dark=(0, 0, 0), bg_light=(255, 255, 255)):
    """Edge width = semi-transparent pixels per pixel of outline length; halo = mean |colour| shift of
    edge pixels composited over black vs white relative to the nearest opaque neighbour colour."""
    a = rgba[..., 3].astype(np.float32) / 255
    semi = (a > 0.02) & (a < 0.98)
    solid = a >= 0.98
    border = solid & ~(np.roll(solid, 1, 0) & np.roll(solid, -1, 0) & np.roll(solid, 1, 1) & np.roll(solid, -1, 1))
    width = float(semi.sum() / max(1, border.sum()))
    rgb = rgba[..., :3].astype(np.float32)
    ref = np.zeros_like(rgb)
    cnt = np.zeros(a.shape, np.float32)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        sk = np.roll(np.roll(solid, dy, 0), dx, 1)
        ref += np.roll(np.roll(rgb, dy, 0), dx, 1) * sk[..., None]
        cnt += sk
    has = semi & (cnt > 0)
    if not has.any():
        return dict(edge_width=round(width, 2), halo=0.0)
    refc = ref[has] / cnt[has][:, None]
    halo = float(np.abs(rgb[has] - refc).mean() / 255)
    return dict(edge_width=round(width, 2), halo=round(halo, 3))
