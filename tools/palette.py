"""CustomSlop colour schemes: a broad palette, 1-3 colours per weapon, hue-repeat avoidance.

Palette families: full hue wheel (saturated), pastels, neon, metals (gold, silver, copper, bronze,
gunmetal, chrome), wood tones, blacks/whites/greys, team colours (RED/BLU/GRN/YLW), greyscale
(desaturate), and two-colour gradients along the weapon. A scheme assigns colours to regions:
front (barrel/blade), body, accents; the grip keeps its own look (mildly toned).
Used hues are tracked in the catalogue ("used_hues": [[date, hue], ...]); a pick avoids hues within
35 degrees of today's batch and the last 12 weapons.
"""
import colorsys
import math

import numpy as np

TEAM = {"RED": (184, 56, 59), "BLU": (88, 133, 162), "GRN": (90, 150, 70), "YLW": (212, 170, 50)}
METALS = {"gold": (212, 175, 55), "silver": (192, 192, 200), "copper": (184, 115, 51), "bronze": (150, 116, 68),
          "gunmetal": (70, 75, 82), "chrome": (225, 228, 235), "brass": (181, 166, 66)}
WOODS = {"oak": (150, 111, 51), "walnut": (93, 67, 44), "mahogany": (103, 43, 32), "birch": (215, 190, 140),
         "cherry": (140, 58, 38)}
NEUTRALS = {"black": (25, 25, 28), "white": (235, 235, 230), "grey": (128, 128, 128), "charcoal": (55, 55, 58)}
FAMILY_W = {"hue": 0.24, "pastel": 0.12, "neon": 0.10, "metal": 0.14, "wood": 0.10, "neutral": 0.10,
            "team": 0.08, "greyscale": 0.05, "gradient": 0.07}


def hsv(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def hue_of(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0 if s > 0.25 and v > 0.2 else None


def hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def colour(rng, family, avoid):
    for _ in range(30):
        if family == "hue":
            c = hsv(rng.uniform(0, 360), rng.uniform(0.6, 0.95), rng.uniform(0.55, 0.95))
        elif family == "pastel":
            c = hsv(rng.uniform(0, 360), rng.uniform(0.2, 0.4), rng.uniform(0.85, 1.0))
        elif family == "neon":
            c = hsv(rng.uniform(0, 360), 1.0, 1.0)
        elif family == "metal":
            c = METALS[rng.choice(sorted(METALS))]
        elif family == "wood":
            c = WOODS[rng.choice(sorted(WOODS))]
        elif family == "neutral":
            c = NEUTRALS[rng.choice(sorted(NEUTRALS))]
        elif family == "team":
            c = TEAM[rng.choice(sorted(TEAM))]
        else:
            c = None
        h = hue_of(c) if c else None
        if h is None or all(hue_dist(h, a) >= 35 for a in avoid):
            return c
    return c


def scheme(rng, avoid_hues):
    """-> dict(regions -> op), list of hues used. op kinds: tint (rgb, strength), greyscale,
    gradient (rgb_a -> rgb_b along the weapon), keep."""
    n = rng.choices([1, 2, 3], weights=[0.3, 0.45, 0.25])[0]
    fams = [rng.choices(list(FAMILY_W), weights=list(FAMILY_W.values()))[0] for _ in range(n)]
    ops, used = [], []
    for f in fams:
        if f == "greyscale":
            ops.append(dict(kind="greyscale", strength=round(rng.uniform(0.6, 1.0), 2), contrast=round(rng.uniform(0.9, 1.3), 2)))
            continue
        if f == "gradient":
            a = colour(rng, rng.choice(["hue", "neon", "pastel", "metal"]), avoid_hues + used)
            if hue_of(a) is not None:
                used.append(hue_of(a))
            b = colour(rng, rng.choice(["hue", "neon", "pastel", "metal", "neutral"]), avoid_hues + used)
            if hue_of(b) is not None:
                used.append(hue_of(b))
            ops.append(dict(kind="gradient", a=a, b=b, strength=round(rng.uniform(0.6, 0.95), 2), family=f))
            continue
        c = colour(rng, f, avoid_hues + used)
        if hue_of(c) is not None:
            used.append(hue_of(c))
        ops.append(dict(kind="tint", rgb=c, strength=round(rng.uniform(0.55, 0.95), 2), family=f,
                        brightness=round(rng.uniform(0.85, 1.2), 2)))
    regions = ["front", "body", "accent"]
    rng.shuffle(regions)
    assign = {r: ops[i % len(ops)] for i, r in enumerate(regions)}
    assign["grip"] = rng.choice([dict(kind="keep"), dict(kind="greyscale", strength=0.5, contrast=1.0),
                                 dict(ops[0], strength=round(ops[0].get("strength", 0.6) * 0.4, 2))])
    return assign, used


def apply_op(rgb, op, t=None):
    """rgb float HxWx3 in 0..1; t = per-texel position 0..1 along the weapon (for gradients)."""
    k = op.get("kind")
    if k in (None, "keep"):
        return rgb
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])[..., None]
    if k == "greyscale":
        g = np.clip((lum - 0.5) * op.get("contrast", 1.0) + 0.5, 0, 1)
        s = op["strength"]
        return rgb * (1 - s) + g * s
    if k == "tint":
        c = np.array(op["rgb"], dtype=np.float32) / 255.0
        target = np.clip(lum * c / max(0.25, float(c.mean())) * 0.9 * op.get("brightness", 1.0), 0, 1)
        s = op["strength"]
        return rgb * (1 - s) + target * s
    if k == "gradient":
        ca, cb = np.array(op["a"], np.float32) / 255, np.array(op["b"], np.float32) / 255
        tt = (t if t is not None else np.full(rgb.shape[:2], 0.5))[..., None]
        c = ca * (1 - tt) + cb * tt
        target = np.clip(lum * c / np.maximum(0.25, c.mean(-1, keepdims=True)) * 0.9, 0, 1)
        s = op["strength"]
        return rgb * (1 - s) + target * s
    return rgb
