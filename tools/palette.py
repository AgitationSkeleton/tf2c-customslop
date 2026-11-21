"""CustomSlop colour schemes, v4 (2026-11-21).

User: "Colors should be more solid, vibrant palette changes that cover whole regions and not just
small strips with bad speckling, allowing for a more matte recolor. Variety should also be
encouraged to prevent it looking too similar to a recent recolor of the same model." (reference:
TF2's team-coloured Scattergun / Rocket Launcher - every painted part one flat colour, wood kept.)

How a weapon is painted:
  1. regions.island_map splits each texture into UV islands (connected pieces of the model's UV
     layout). An island is ALWAYS painted as one unit: no per-texel decisions, so no speckle and
     no strips along triangle edges.
  2. Islands are grouped into MATERIALS by their mean source colour (area-weighted k-means, merged
     when close): e.g. painted metal / bare metal / wood / rubber.
  3. The scheme paints materials solid: the largest paintable material gets the main colour, the
     others the second/third colours (or the main colour again), natural materials (wood, leather)
     are kept as they are or painted (random per weapon). Optional extras, each per whole island:
     front/back two-tone along the weapon (e.g. a barrel in a second colour), accent colour on
     small parts (sights, screws, levers), grip kept / painted.
  4. Paint is matte: flat colour x the island's own shading (source luminance relative to the
     island mean, compressed), so detail and wear read through but the colour is solid.
Colours are vivid by default (random hue, high saturation), with occasional pastel, dark, metal,
white/black and wood swatches; extra colours follow a random harmony.
Variety: the main hue avoids today's batch and the last 12 weapons by 35 degrees, and avoids the
hues of earlier recolours of the SAME donor model by 70 degrees.
Old v2 kinds (tint, gradient, greyscale, keep) still apply for summaries written before v4.
"""
import colorsys

import numpy as np

VERSION = 4
TEAM = {"RED": (184, 56, 59), "BLU": (88, 133, 162), "GRN": (90, 150, 70), "YLW": (212, 170, 50)}
METALS = {"gold": (212, 175, 55), "silver": (192, 192, 200), "copper": (184, 115, 51), "bronze": (150, 116, 68),
          "gunmetal": (70, 75, 82), "chrome": (225, 228, 235), "brass": (181, 166, 66),
          "rose gold": (183, 110, 121), "blued steel": (60, 75, 110)}
WOODS = {"oak": (150, 111, 51), "walnut": (93, 67, 44), "mahogany": (103, 43, 32), "birch": (215, 190, 140),
         "cherry": (140, 58, 38)}
NEUTRALS = {"black": (32, 32, 36), "white": (205, 205, 198), "grey": (110, 110, 110)}
SOURCE_W = {"vivid": 0.52, "deep": 0.22, "pastel": 0.06, "neon": 0.04, "metal": 0.08, "neutral": 0.05,
            "wood": 0.02, "team": 0.02}
HARMONY_W = {"independent": 0.30, "complementary": 0.18, "analogous": 0.16, "triadic": 0.14, "split": 0.10,
             "monochrome": 0.12}
FINISH_W = {"matte": 0.75, "satin": 0.17, "metallic": 0.08}


# ------------------------------------------------------------------ colours
def hsv(h, s, v):
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, min(1, max(0, s)), min(1, max(0, v)))
    return (int(r * 255), int(g * 255), int(b * 255))


def hue_of(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0 if s > 0.25 and v > 0.2 else None


def hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _pick(rng, weights):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def colour(rng, family, avoid=(), hue=None, gap=35):
    c = None
    for _ in range(40):
        h = hue if hue is not None else rng.uniform(0, 360)
        if family in ("vivid", "hue", "any"):
            c = hsv(h, rng.uniform(0.6, 1.0), rng.uniform(0.45, 0.8))
        elif family == "deep":
            c = hsv(h, rng.uniform(0.55, 0.95), rng.uniform(0.28, 0.48))
        elif family == "pastel":
            c = hsv(h, rng.uniform(0.3, 0.55), rng.uniform(0.7, 0.85))
        elif family == "neon":
            c = hsv(h, 1.0, rng.uniform(0.8, 0.95))
        elif family == "metal":
            c = METALS[rng.choice(sorted(METALS))]
        elif family == "wood":
            c = WOODS[rng.choice(sorted(WOODS))]
        elif family == "team":
            c = TEAM[rng.choice(sorted(TEAM))]
        else:
            c = NEUTRALS[rng.choice(sorted(NEUTRALS))]
        hh = hue_of(c)
        if hue is not None or (hh is not None and all(hue_dist(hh, a) >= gap for a in avoid)):
            return c
        if hh is None and not avoid:
            return c
    return c


def scheme(rng, avoid_hues, donor_hues=()):
    """-> (scheme dict, hues used). donor_hues: main hues of earlier recolours of this donor."""
    harmony = _pick(rng, HARMONY_W)
    fam = _pick(rng, SOURCE_W)
    main = None
    for _ in range(40):                    # main colour: away from recent hues and this donor's past
        main = colour(rng, fam, avoid_hues)
        h = hue_of(main)
        if h is None or all(hue_dist(h, d) >= 70 for d in donor_hues):
            break
        fam = rng.choice(["vivid", "deep", "pastel", "neon"])
    h0 = hue_of(main)
    if h0 is None:
        h0 = rng.uniform(0, 360)
    offs = {"complementary": [180, 180, 0], "analogous": [35, -35, 70], "triadic": [120, 240, 120],
            "split": [150, 210, 180]}.get(harmony)
    others = []
    for i in range(3):
        if harmony == "independent":
            others.append(colour(rng, _pick(rng, SOURCE_W)))
        elif harmony == "monochrome":
            others.append(hsv(h0 + rng.uniform(-10, 10), rng.uniform(0.4, 1.0), rng.uniform(0.25, 0.8)))
        else:
            others.append(colour(rng, rng.choice(["vivid", "vivid", "deep", "deep", "pastel"]),
                                 hue=h0 + offs[i] + rng.uniform(-12, 12)))
    s = dict(_v=4, harmony=harmony, paints=[main] + others,
             second_same=rng.random() < 0.3,                 # 2nd material painted the main colour too
             keep_natural=rng.random() < 0.55,               # wood / leather left as they are
             two_tone=dict(at=round(rng.uniform(0.5, 0.72), 2), paint=rng.choice([1, 2])) if rng.random() < 0.3 else None,
             accent=rng.choice([1, 2, 3]) if rng.random() < 0.45 else None,
             grip=rng.choices(["same", "keep", "paint"], weights=[0.5, 0.25, 0.25])[0],
             detail=round(rng.uniform(0.6, 0.9), 2),
             finish=_pick(rng, FINISH_W))
    hues = [h for h in (hue_of(c) for c in s["paints"]) if h is not None]
    return s, hues[:2]


# ------------------------------------------------------------------ materials + painting
def _lum(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _feat(c):
    """Perceptual-ish feature of a mean colour (0..1 rgb): luminance + two chroma axes."""
    r, g, b = c
    return np.array([0.299 * r + 0.587 * g + 0.114 * b, (r - g) * 0.8, ((r + g) / 2 - b) * 0.8])


def is_natural(c):
    h, s, v = colorsys.rgb_to_hsv(*[float(x) for x in c])
    return 8 / 360 <= h <= 50 / 360 and 0.22 <= s <= 0.8 and 0.12 <= v <= 0.85


def materials(stats, kmax=4, merge=0.09):
    """stats: list of (key, mean rgb 0..1, area). -> {key: material index}, materials list
    [dict(mean, area, natural)] sorted by area, largest first. Area-weighted k-means."""
    if not stats:
        return {}, []
    X = np.array([_feat(c) for _, c, _ in stats])
    W = np.array([max(a, 1e-9) for _, _, a in stats])
    k = min(kmax, len(stats))
    cent = [X[int(W.argmax())]]
    while len(cent) < k:                                     # farthest-point init (deterministic)
        d = np.min([((X - c) ** 2).sum(1) for c in cent], 0)
        if d.max() < merge ** 2:
            break
        cent.append(X[int(d.argmax())])
    C = np.array(cent)
    for _ in range(20):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        C = np.array([np.average(X[lab == j], 0, W[lab == j]) if (lab == j).any() else C[j] for j in range(len(C))])
    # merge close materials
    j = 0
    while j < len(C):
        close = [i for i in range(j + 1, len(C)) if np.sqrt(((C[i] - C[j]) ** 2).sum()) < merge]
        for i in reversed(close):
            lab[lab == i] = j
            lab[lab > i] -= 1
            C = np.delete(C, i, 0)
        j += 1
    mats = []
    for j in range(len(C)):
        sel = lab == j
        rgbm = np.average(np.array([c for _, c, _ in stats])[sel], 0, W[sel])
        mats.append(dict(mean=rgbm, area=float(W[sel].sum()), natural=is_natural(rgbm), old=j))
    order = sorted(range(len(mats)), key=lambda j: -mats[j]["area"])
    remap = {o: n for n, o in enumerate(order)}
    return {stats[i][0]: remap[int(lab[i])] for i in range(len(stats))}, [mats[o] for o in order]


def material_paints(s, mats):
    """Material index -> rgb (0..255) or None (keep). The largest paintable material gets the main
    colour; a material that covers most of the weapon is always painted (solid coverage)."""
    out, n = {}, 0
    total = sum(m["area"] for m in mats) or 1
    for j, m in enumerate(mats):
        if m["natural"] and s["keep_natural"] and m["area"] / total < 0.6:
            out[j] = None
            continue
        if n == 0:
            out[j] = s["paints"][0]
        elif n == 1 and s["second_same"]:
            out[j] = s["paints"][0]
        else:
            out[j] = s["paints"][min(n, len(s["paints"]) - 1)]
        n += 1
    if all(v is None for v in out.values()) and mats:
        out[0] = s["paints"][0]
    return out


def island_paint(s, base, station, label, share):
    """Per-island override of its material's paint (whole island): grip, accent, two-tone."""
    if label == 0:                                           # grip
        if s["grip"] == "keep":
            return None
        if s["grip"] == "paint":
            return s["paints"][-1]
    if s.get("accent") and (label == 1 or share < 0.004):
        return s["paints"][s["accent"]]
    if base is not None and s.get("two_tone") and station > s["two_tone"]["at"]:
        return s["paints"][s["two_tone"]["paint"]]
    return base


def paint(rgb, mask, colour, s):
    """Solid matte paint of colour over mask (bool/0..1), keeping the region's own shading."""
    c = np.array(colour, np.float32) / 255.0
    L = _lum(rgb)
    sel = L[mask > 0.5]
    mean = float(np.median(sel)) if sel.size else 0.5
    shade = L / max(mean, 0.04)
    shade = 1 + (np.clip(shade, 0.3, 1.6) - 1) * s.get("detail", 0.75)
    shade = shade * 0.92                                     # paint sits slightly under the light
    out = c[None, None, :] * shade[..., None]
    fin = s.get("finish", "matte")
    if fin == "satin":
        out = out + np.clip(shade - 1.1, 0, 1)[..., None] * 0.2
    elif fin == "metallic":
        out = out * (0.75 + 0.5 * np.clip(shade - 0.6, 0, 1)[..., None]) + np.clip(shade - 1.2, 0, 1)[..., None] * 0.35
    out = np.clip(out, 0.05, 1)
    m = mask[..., None].astype(np.float32)
    return rgb * (1 - m) + out * m


def textureless_colour(s):
    """$color2 for a material with no base texture (TF2C's flat 'black'): the main paint, darkened."""
    c = s.get("paints", [None])[0] if s.get("_v") == 4 else None
    if c is None:
        op = s.get("body") or {}
        c = op.get("rgb") or op.get("a") or (60, 60, 60)
    return "[%.3f %.3f %.3f]" % tuple(max(0.06, x / 255.0) * 0.5 for x in c)


# ------------------------------------------------------------------ v2 ops (old summaries)
def apply_op(rgb, op, t=None, mask=None):
    k = op.get("kind")
    if k in (None, "keep"):
        return rgb
    lum = _lum(rgb)[..., None]
    s = op.get("strength", 1.0)
    if k == "greyscale":
        g = np.clip((lum - 0.5) * op.get("contrast", 1.0) + 0.5, 0, 1)
        return rgb * (1 - s) + g * s
    if k == "tint":
        c = np.array(op["rgb"], dtype=np.float32) / 255.0
        target = np.clip(lum * c / max(0.25, float(c.mean())) * 0.9 * op.get("brightness", 1.0), 0, 1)
        return rgb * (1 - s) + target * s
    if k == "gradient":
        ca, cb = np.array(op["a"], np.float32) / 255, np.array(op["b"], np.float32) / 255
        tt = (t if t is not None else np.full(rgb.shape[:2], 0.5))[..., None]
        c = ca * (1 - tt) + cb * tt
        target = np.clip(lum * c / np.maximum(0.25, c.mean(-1, keepdims=True)) * 0.9, 0, 1)
        return rgb * (1 - s) + target * s
    return rgb
