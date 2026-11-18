"""Audit every donor's fitted icon camera: render the UNMODIFIED donor with its cached camera next to
its own source icon and flag poses that are wrong.

Flags (per donor):
  low_iou      canvas IoU < 0.7
  mirrored     the horizontally flipped icon matches the render clearly better (backwards)
  flipped_v    the vertically flipped icon matches clearly better (upside-down)
  axis_off     principal-axis angle of render vs icon differs > 20 deg (rotated)
  aspect_off   silhouette elongation differs > 1.8x (top-down / end-on views of a long weapon)
Writes icon_audit_v<N>.json and icon_audit_v<N>.png (source icon | render, flags) in the research root.
Read-only on state/ and queue/; reads cache/icon_fit/<key>_v<N>.json.

  python -I audit_icons.py [--version 2] [--only key,key] [--compare 2,3]
"""
import argparse
import json
import math
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fit_icons  # noqa: E402
import iconfit as IF  # noqa: E402
import pipeline  # noqa: E402
import slopqueue as Q  # noqa: E402
import srcmodel as S  # noqa: E402
import vmrender  # noqa: E402

HUD = (40, 40, 40, 255)


def shape_stats(mask):
    ys, xs = np.nonzero(mask > 0.5)
    if len(xs) < 20:
        return None
    pts = np.stack([xs, -ys], 1).astype(np.float64)
    c = pts - pts.mean(0)
    ev, evec = np.linalg.eigh(c.T @ c / len(c))
    v = evec[:, -1]
    ang = math.degrees(math.atan2(v[1], v[0])) % 180
    elong = math.sqrt(max(ev[-1], 1e-9) / max(ev[0], 1e-9))
    return dict(angle=ang, elong=elong)


def load_model(ctx, d, f):
    tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
    kind = (f or {}).get("model_kind", "w")
    rel = d["mp"] if kind == "v" or not d.get("mw") else d["mw"]
    m = S.load(pipeline.extract_model(ctx, rel, tmp))
    if os.path.basename(rel).lower().startswith("v_"):
        m = IF.posed(m)
    return m


def audit_one(ctx, d, version):
    key = "%s:%s" % (d["src"], d["id"])
    cp = IF.cache_path(key, version)
    if not os.path.exists(cp):
        return None
    f = json.load(open(cp))
    saved, ctx.fs = ctx.fs, d["fs"]
    try:
        icon, why = fit_icons.source_icon(ctx, d)
        if icon is None:
            return None
        m = load_model(ctx, d, f)
        tex = vmrender.textures_for(ctx, m, None)
        mats = vmrender.materials_for(ctx, m, None)
    finally:
        ctx.fs = saved
    img = IF.render_icon(m, tex, f, mats=mats)
    ra = np.asarray(img)[..., 3] / 255.0
    ia = icon[..., 3] / 255.0
    iou = IF.iou(ra, ia)
    lr, li = IF.letterbox_mask(ra), IF.letterbox_mask(ia)
    l_iou = IF.iou(lr, li)
    l_h = IF.iou(lr, li[:, ::-1])
    l_v = IF.iou(lr, li[::-1, :])
    sr, si = shape_stats(ra), shape_stats(ia)
    flags = []
    if iou < 0.7:
        flags.append("low_iou")
    if l_h > l_iou + 0.05:
        flags.append("mirrored")
    if l_v > l_iou + 0.05:
        flags.append("flipped_v")
    if sr and si:
        da = abs(sr["angle"] - si["angle"])
        da = min(da, 180 - da)
        if da > 20 and si["elong"] > 1.6:
            flags.append("axis_off")
        if max(sr["elong"], si["elong"]) / max(1e-6, min(sr["elong"], si["elong"])) > 1.8:
            flags.append("aspect_off")
    return dict(key=key, icon_src=why, iou=round(iou, 3), iou_letterbox=round(l_iou, 3),
                iou_if_mirrored=round(l_h, 3), iou_if_upside_down=round(l_v, 3), flags=flags,
                model_kind=f.get("model_kind"), name=d["kv"].get("item_name") or d["kv"].get("name"),
                img=img, icon=icon)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=2)
    ap.add_argument("--only")
    ap.add_argument("--compare", help="e.g. 2,3: sheet with icon | v2 render | v3 render")
    a = ap.parse_args()
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    keys = a.only.split(",") if a.only else None
    vers = [int(x) for x in a.compare.split(",")] if a.compare else [a.version]
    rows = []
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        if keys and key not in keys:
            continue
        res = [audit_one(ctx, d, v) for v in vers]
        if all(r is None for r in res):
            continue
        rows.append((key, res))
        print(key, [(r["iou"], r["flags"]) if r else None for r in res], flush=True)
    tag = "_".join(str(v) for v in vers)
    js = [dict(key=k, **{"v%d" % v: ({kk: vv for kk, vv in r.items() if kk not in ("img", "icon")} if r else None)
                        for v, r in zip(vers, res)}) for k, res in rows]
    json.dump(js, open(os.path.join(ROOT, "icon_audit_v%s.json" % tag), "w"), indent=1)
    T = 200
    cols = 1 + len(vers)
    sh = Image.new("RGBA", (T * cols + 10 * (cols + 1) + 420, (T + 10) * len(rows) + 10), HUD)
    dr = ImageDraw.Draw(sh)
    y = 10
    for key, res in rows:
        icon = next(r["icon"] for r in res if r)
        tiles = [Image.fromarray(icon, "RGBA")] + [r["img"] if r else None for r in res]
        for k, im in enumerate(tiles):
            if im is None:
                continue
            bg = Image.new("RGBA", (T, T), HUD)
            bg.alpha_composite(im.convert("RGBA").resize((T, T), Image.LANCZOS))
            sh.paste(bg, (10 + k * (T + 10), y))
        tx = 10 + cols * (T + 10)
        dr.text((tx, y + 4), key, fill=(255, 255, 255, 255))
        for j, (v, r) in enumerate(zip(vers, res)):
            if r:
                col = (255, 120, 120, 255) if r["flags"] else (150, 230, 150, 255)
                dr.text((tx, y + 24 + 18 * j), "v%d IoU %.2f %s" % (v, r["iou"], ",".join(r["flags"]) or "ok"), fill=col)
        r0 = next(r for r in res if r)
        dr.text((tx, y + 24 + 18 * len(vers)), (r0["icon_src"] or "")[:60], fill=(180, 180, 180, 255))
        y += T + 10
    sh.save(os.path.join(ROOT, "icon_audit_v%s.png" % tag))
    print("wrote icon_audit_v%s.png" % tag)


if __name__ == "__main__":
    main()
