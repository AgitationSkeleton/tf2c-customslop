"""Calibrate + report the v2 icon renderer against REAL icons of unmodified donors.

For each donor with its own source-game icon (TF2C backpack icons, April Fools icons, Open
Fortress bucket sprites, TF2 Classic beta sprites, tf2cc-staged icons):
  * pose: v2 silhouette fit to that icon (cache/icon_fit/<key>_v2.json); "before" = the v1 fit
  * light rig: ONE global srcshade rig fitted so renders match the icons' colour statistics
    (mean, saturation, near-black share, luminance histogram) -> cache/icon_fit/_rig_v2.json
  * report: IoU (v1 vs v2 pose), colour stats (v1 vs v2 vs real), edge width / halo on the 256 px
    shipped icon (v1: straight-alpha Lanczos; v2: premultiplied box + edge bleed) vs the real icon
  * sheet: real icon | old render | new render (over the HUD grey) -> render_calibration.png
Nothing is published or applied.

  python -I calibrate_render.py [--only key,key] [--iters 400]
"""
import argparse
import json
import os
import random
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
import srcshade as SS  # noqa: E402
import vmrender  # noqa: E402

DEFAULT_KEYS = ["of_merc:30114", "of_merc:30100", "of_merc:30117", "of_merc:30120", "tf2c:18", "tf2c:13", "tf2c:7",
                "tf2c:21", "tf2c:24", "tf2c:19", "tf2c:6", "tf2c:2013", "aprilfools:17502", "aprilfools:17509",
                "tf2classic_b4:90006", "tf2classic_b4:90001"]
HUD = (40, 40, 40, 255)


def loss(st, ref):
    return (abs(st["luma"] - ref["luma"]) / 255 * 2 + abs(st["sat"] - ref["sat"]) * 2
            + abs(st["near_black"] - ref["near_black"]) + SS.hist_dist(st, ref))


def ship_icon_v1(img):
    return np.asarray(img.convert("RGBA").resize((256, 256), Image.LANCZOS))


def ship_icon_v2(img):
    return SS.bleed_edges(SS.resize_premul(np.asarray(img.convert("RGBA")), (256, 256)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--iters", type=int, default=400)
    a = ap.parse_args()
    keys = a.only.split(",") if a.only else DEFAULT_KEYS
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    rng = random.Random(7)
    rows = []
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        if key not in keys:
            continue
        saved, ctx.fs = ctx.fs, d["fs"]
        try:
            icon, why = fit_icons.source_icon(ctx, d)
            if icon is None:
                print(key, "no icon")
                continue
            cp2 = IF.cache_path(key, 2)
            f2 = json.load(open(cp2)) if os.path.exists(cp2) else fit_icons.fit_donor_v2(ctx, d, random.Random(7))[1]
            tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
            rel = d["mp"] if (f2 or {}).get("model_kind") == "v" else (d["mw"] or d["mp"])
            m = S.load(pipeline.extract_model(ctx, rel, tmp))
            if (f2 or {}).get("model_kind") == "v":
                m = IF.posed(m)
            tex = vmrender.textures_for(ctx, m, None)
            mats = vmrender.materials_for(ctx, m, None)
        finally:
            ctx.fs = saved
        cp1 = IF.cache_path(key, 1)
        f1 = json.load(open(cp1)) if os.path.exists(cp1) else None
        old = IF.render_icon(m, tex, f1, legacy=True) if f1 else None
        buf = IF.raster_buffers(m, np.array(f2["R"]), 512, scale=f2["scale"], centre=tuple(f2["centre"]),
                                textures=tex, mirror=f2["mirror"], persp=tuple(f2["persp"]) if f2.get("persp") else None)
        ia = icon[..., 3].astype(np.float32) / 255
        old_iou = None
        if old is not None:
            old_iou = IF.iou(np.asarray(old)[..., 3].astype(np.float32) / 255, ia)
        rows.append(dict(key=key, src=why, icon=icon, m=m, tex=tex, mats=mats, f1=f1, f2=f2, old=old, buf=buf,
                         ref=SS.stats(icon), iou_old=old_iou, iou_new=IF.iou(buf["alpha"], ia)))
        print(key, why, "iou old %s new %.3f" % (None if old_iou is None else round(old_iou, 3), rows[-1]["iou_new"]))

    def total(R, only=None):
        ls = []
        for r in rows:
            if only and not r["key"].startswith(only):
                continue
            b = r["buf"]
            col = SS.shade(b["nrm"], b["alb"], b["balpha"], b["uv"], b["matid"], b["alpha"], r["mats"], R)
            img = np.dstack([col * 255, b["alpha"] * 255]).astype(np.uint8)
            st = SS.stats(img)
            if st and r["ref"]:
                ls.append(loss(st, r["ref"]))
        return float(np.mean(ls))
    R = dict(SS.DEFAULT_RIG)
    if os.path.exists(SS.RIG_PATH):                     # continue from the last calibration
        R.update(json.load(open(SS.RIG_PATH)).get("rig", {}))
    R["spec"] = max(R["spec"], 0.25)
    best = (total(R), dict(R))
    space = [("key_az", 40, -180, 180), ("key_el", 12, -10, 80), ("key", .4, 0.3, 6), ("fill", .2, 0, 2),
             ("amb_top", .05, 0, .8), ("amb_bot", .03, 0, .5), ("rim", .3, 0, 3), ("spec", .3, 0.25, 3),
             ("exposure", .15, .3, 3), ("warp_srgb", .6, 0, 1), ("warp_fallback", .6, 0, 1), ("env", .1, 0, 1),
             ("full_everywhere", .6, 0, 1)]
    for it in range(a.iters):
        T = dict(best[1])
        for k, sd, lo, hi in space:
            if rng.random() < 0.35:
                T[k] = float(np.clip(T[k] + rng.gauss(0, sd) * (1 - it / (a.iters * 1.2)), lo, hi))
        s = total(T)
        if s < best[0]:
            best = (s, T)
            print("it %d loss %.4f" % (it, s))
    rig = best[1]
    # which lighting model matches each source game's real icons (lower loss = closer)
    modes = {}
    for src in sorted({r["key"].split(":")[0] for r in rows}):
        modes[src] = {}
        for name, over in (("tf2c_rules_half_with_phong", dict(full_everywhere=0.0)),
                           ("full_lambert_everywhere", dict(full_everywhere=1.0))):
            for wf in (0.0, 1.0):
                modes[src]["%s%s" % (name, "+fallback_warp" if wf else "")] = round(total(dict(rig, warp_fallback=wf, **over), src + ":"), 4)
    json.dump(dict(rig=rig, loss=best[0], donors=[r["key"] for r in rows], lighting_model_loss_by_source=modes),
              open(SS.RIG_PATH, "w"), indent=1)
    # final renders + report
    rep, tiles = [], []
    for r in rows:
        new = IF.render_icon(r["m"], r["tex"], r["f2"], mats=r["mats"], rig=rig)
        e_real = SS.edge_stats(np.asarray(Image.fromarray(r["icon"], "RGBA").resize((256, 256), Image.LANCZOS)))
        e_old = SS.edge_stats(ship_icon_v1(r["old"])) if r["old"] is not None else None
        e_new = SS.edge_stats(ship_icon_v2(new))
        s_old = SS.stats(np.asarray(r["old"])) if r["old"] is not None else None
        s_new = SS.stats(np.asarray(new))
        strip = lambda s: {k: v for k, v in s.items() if k != "hist"} if s else None    # noqa: E731
        rep.append(dict(donor=r["key"], icon=r["src"], iou_old=None if r["iou_old"] is None else round(r["iou_old"], 3),
                        iou_new=round(IF.iou(np.asarray(new)[..., 3] / 255.0, r["icon"][..., 3] / 255.0), 3),
                        real=strip(r["ref"]), old=strip(s_old), new=strip(s_new),
                        hist_dist_old=round(SS.hist_dist(s_old, r["ref"]), 3) if s_old else None,
                        hist_dist_new=round(SS.hist_dist(s_new, r["ref"]), 3),
                        edges_real=e_real, edges_old=e_old, edges_new=e_new))
        tiles.append((r["key"], rep[-1], Image.fromarray(r["icon"], "RGBA"), r["old"], new))
    out = dict(rig=rig, rig_loss=round(best[0], 4), rig_loss_without_specular=round(total(dict(rig, spec=0.0)), 4),
               lighting_model_loss_by_source=modes, donors=rep)
    json.dump(out, open(os.path.join(ROOT, "render_calibration.json"), "w"), indent=1)
    T_ = 256
    sh = Image.new("RGBA", (T_ * 3 + 20, (T_ + 34) * len(tiles) + 30), HUD)
    dr = ImageDraw.Draw(sh)
    dr.text((8, 6), "real icon (donor's own game)          | old render (v1)                       | new render (v2)", fill=(230, 230, 230, 255))
    y = 26
    for key, rr, ic, old, new in tiles:
        for k, im in enumerate((ic, old, new)):
            if im is None:
                continue
            bg = Image.new("RGBA", (T_, T_), HUD)
            bg.alpha_composite(im.convert("RGBA").resize((T_, T_), Image.LANCZOS))
            sh.paste(bg, (5 + k * (T_ + 5), y))
        txt = "%s  IoU %s -> %s | sat real %.2f old %s new %.2f | near-black real %.2f old %s new %.2f" % (
            key, rr["iou_old"], rr["iou_new"], rr["real"]["sat"], rr["old"]["sat"] if rr["old"] else "-", rr["new"]["sat"],
            rr["real"]["near_black"], rr["old"]["near_black"] if rr["old"] else "-", rr["new"]["near_black"])
        dr.text((8, y + T_ + 4), txt, fill=(230, 230, 230, 255))
        y += T_ + 34
    sh.save(os.path.join(ROOT, "render_calibration.png"))
    print(json.dumps(dict(rig=rig, loss=best[0]), indent=1))


if __name__ == "__main__":
    main()
