"""Fit the icon style of donors to their stock icons (cache/icon_fit/) and make a comparison sheet.

  python -I fit_icons.py [--sheet] [--only src:id,src:id] [--all]
Sheet: proto/render/iconfit_sheet.png = stock icon | our render of the unmodified donor (fitted) |
our render of a mutated copy (same fitted camera + lighting), with the fit scores.
"""
import argparse
import collections
import json
import os
import random
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import iconfit as IF  # noqa: E402
import mutate as MU  # noqa: E402
import pipeline  # noqa: E402
import slopqueue  # noqa: E402
import srcmodel as S  # noqa: E402
import vmrender  # noqa: E402
import vtf  # noqa: E402

SAMPLE = ["tf2c:13", "tf2c:18", "tf2c:2001", "tf2c:21", "tf2c:24", "tf2c:2016", "aprilfools:17502", "tf2c:2013",
          "tf2c:6", "tf2c:19"]


def stock_icon(ctx, d):
    img = d["kv"].get("image_inventory")
    if not img:
        return None
    for suf in ("_large", "", "_red", "_blue"):
        raw = ctx.fs.read("materials/" + img.replace("\\", "/") + suf + ".vtf")
        if raw is None and "/" in img:
            base = img.replace("\\", "/")
            raw = ctx.fs.read("materials/" + os.path.dirname(base) + "/red/" + os.path.basename(base) + "_red.vtf")
        if raw is not None:
            return np.asarray(Image.fromarray(vtf.decode(raw)[2], "RGBA").resize((512, 512), Image.LANCZOS))
    return None


def fit_donor(ctx, d, rng):
    key = "%s:%s" % (d["src"], d["id"])
    icon = stock_icon(ctx, d)
    if icon is None:
        return key, None, None
    tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
    try:
        src = pipeline.extract_model(ctx, d["mw"] or d["mp"], tmp)
        m = S.load(src)
        tex = vmrender.textures_for(ctx, m, None)
        f = IF.fit(m, tex, icon, rng)
        if f:
            f["donor"] = key
            f["model"] = d["mw"] or d["mp"]
            os.makedirs(IF.CACHE, exist_ok=True)
            json.dump(f, open(IF.cache_path(key), "w"), indent=1)
        return key, f, (icon, m, tex, src)
    finally:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    c = slopqueue.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    rng = random.Random(7)
    keys = a.only.split(",") if a.only else (None if a.all else SAMPLE)
    donors = [d for d in ctx.donors if keys is None or "%s:%s" % (d["src"], d["id"]) in keys]
    rows, fam_fits = [], collections.defaultdict(list)
    for d in donors:
        saved, ctx.fs = ctx.fs, d["fs"]
        try:
            key, f, extra = fit_donor(ctx, d, rng)
        finally:
            ctx.fs = saved
        if not f:
            print(key, "no stock icon")
            continue
        fam_fits[d["fam"]].append(f)
        print(key, f["scores"], {k: f[k] for k in ("yaw", "pitch", "roll")})
        if a.sheet:
            icon, m, tex, src = extra
            ours = IF.render_icon(m, tex, f)
            mt = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
            MU.mutate(src, mt, "models/customslop/fit/x.mdl", "models/customslop/fit",
                      dict(droop=0.2, flare=1.4, stretch=1.3, pivot=0.4))
            mm = S.load(os.path.join(mt, "models/customslop/fit/x.mdl"))
            mut = IF.render_icon(mm, tex, f)
            rows.append((key, f["scores"], Image.fromarray(icon, "RGBA"), ours, mut))
    # family mean lighting (pose is per model; families without fits use the default camera)
    for fam, fs in fam_fits.items():
        L = {k: float(np.mean([f["light"][k] for f in fs])) for k in IF.DEFAULT_LIGHT}
        json.dump(dict(family=fam, light=L, n=len(fs)), open(os.path.join(IF.CACHE, "_family_%s.json" % fam), "w"), indent=1)
    if rows:
        T = 300
        sh = Image.new("RGBA", (T * 3, (T + 24) * len(rows)), (60, 60, 60, 255))
        dr = ImageDraw.Draw(sh)
        for i, (key, sc, ic, ours, mut) in enumerate(rows):
            y = i * (T + 24)
            for j, im in enumerate((ic, ours, mut)):
                sh.alpha_composite(im.resize((T, T)), (j * T, y + 24))
            dr.text((6, y + 5), "%s  stock icon | our render (fitted) | mutated, same camera+light   silhouette IoU %.2f  light SSIM %.2f"
                    % (key, sc["iou_canvas"], sc["light_ssim"]), fill=(255, 255, 255))
        sh.save(os.path.join(ROOT, "proto", "render", "iconfit_sheet.png"))


if __name__ == "__main__":
    main()
