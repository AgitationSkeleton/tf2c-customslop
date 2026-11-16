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


OF_DIR = __import__("cspaths").opt("of_dir")   # optional: Open Fortress game folder (icons)
_OF_ICONS = None


def of_icons():
    """Open Fortress items_game: model basename (w_/v_) -> backpack_icon sprite path."""
    global _OF_ICONS
    if _OF_ICONS is None:
        _OF_ICONS = {}
        p = os.path.join(OF_DIR or "", "scripts", "items", "items_game.txt")
        if OF_DIR and os.path.exists(p):
            import kv
            root = kv.load(p, encoding="utf-8")[0]

            def walk(node, icon):
                own = node.get("backpack_icon") if isinstance(node, kv.KV) else None
                icon = own if isinstance(own, str) else icon
                for k, v in node.pairs:
                    if isinstance(v, kv.KV):
                        walk(v, icon)
                    elif k.lower() in ("playermodel", "viewmodel") and icon:
                        b = os.path.splitext(os.path.basename(v.replace("\\", "/")))[0].lower()
                        _OF_ICONS.setdefault(b, icon)
            walk(root, None)
    return _OF_ICONS


def source_icon(ctx, d):
    """The donor's OWN source-game icon -> (512x512 RGBA, description) or (None, None).
    OF donors: Open Fortress's backpack/bucket sprite for that weapon (found by model name);
    everything else: the donor's own image_inventory read from its own content (TF2C backpack
    icons, April Fools icons, TF2 Classic beta sprites, tf2cc-staged icons)."""
    import re
    if d["src"] in ("of_merc", "marxvee") and OF_DIR:
        for mp in (d.get("mw"), d.get("mp")):
            if not mp:
                continue
            b = re.sub(r"_[0-9a-f]{8}$", "", os.path.splitext(os.path.basename(mp))[0].lower())
            ic = of_icons().get(b)
            if ic:
                rel = os.path.normpath(os.path.join("materials", "backpack", ic.replace("\\", "/"))).replace("\\", "/")
                p = os.path.join(OF_DIR, rel + ".vtf")
                if os.path.exists(p):
                    return IF.square_icon(vtf.decode(open(p, "rb").read())[2]), "Open Fortress " + rel
    img = d["kv"].get("image_inventory")
    for suf in ("_large", "", "_red", "_blue"):
        raw = ctx.fs.read("materials/" + img.replace("\\", "/") + suf + ".vtf") if img else None
        if raw is not None:
            return IF.square_icon(vtf.decode(raw)[2]), "%s materials/%s%s" % (d["src"], img, suf)
    # no icon of its own (presplit / MarxVee / beta models): the nearest same-weapon icon, i.e. the
    # stock TF2C weapon of the same item class (camera style only; its silhouette is approximate)
    ic = d["kv"].get("item_class")
    for k, img2 in stock_icons_by_class().get(ic, []):
        for suf in ("_large", ""):
            raw = ctx.fs.read("materials/" + img2 + suf + ".vtf")
            if raw is not None:
                return IF.square_icon(vtf.decode(raw)[2]), "nearest same-weapon icon: stock 5205 item %s %s" % (k, img2)
    return None, None


_STOCK_ICONS = None


def stock_icons_by_class():
    """item_class -> [(defindex, image_inventory)] of the stock 5205 schema (prefabs resolved)."""
    global _STOCK_ICONS
    if _STOCK_ICONS is None:
        import labels
        from generate import BASE_SCHEMA, load_schema
        sch = load_schema(BASE_SCHEMA)
        pf = {k.lower(): b for k, b in sch.get("prefabs").blocks()} if sch.get("prefabs") else {}
        _STOCK_ICONS = {}
        for k, it in sorted(((k, it) for k, it in sch.get("items").blocks() if k.isdigit()), key=lambda x: int(x[0])):
            c_, im_ = labels._eff(it, "item_class", pf), labels._eff(it, "image_inventory", pf)
            if c_ and im_:
                _STOCK_ICONS.setdefault(c_, []).append((k, im_.replace("\\", "/")))
    return _STOCK_ICONS


def fit_donor_v2(ctx, d, rng):
    """v2: fit the camera to the donor's own source-game icon (cache/icon_fit/<key>_v2.json)."""
    key = "%s:%s" % (d["src"], d["id"])
    icon, why = source_icon(ctx, d)
    if icon is None:
        return key, None, None
    # some games draw their icons from the VIEW model (Open Fortress sprites): try world and view
    # model, keep the better silhouette fit; the mutated weapon is rendered from the same kind
    best = None
    kinds = (("w", d.get("mw")), ("v", d.get("mp"))) if d["src"] in ("of_merc", "marxvee") else (("w", d.get("mw") or d.get("mp")),)
    for kind, rel in kinds:
        if not rel:
            continue
        tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
        src = pipeline.extract_model(ctx, rel, tmp)
        if not os.path.exists(src):
            continue
        m = S.load(src)
        if kind == "v" or os.path.basename(rel).lower().startswith("v_"):
            m = IF.posed(m)                     # view models only make sense in their idle pose
        f = IF.fit_v2(m, icon, rng, icon_src=why, textures=vmrender.textures_for(ctx, m, None))
        if f and (best is None or f["scores"]["iou_canvas"] > best[0]["scores"]["iou_canvas"]):
            f["model_kind"] = kind
            best = (f, m, src, rel)
    if best is None:
        return key, None, None
    f, m, src, rel = best
    if f:
        f["donor"] = key
        f["model"] = rel
        os.makedirs(IF.CACHE, exist_ok=True)
        json.dump(f, open(IF.cache_path(key, 2), "w"), indent=1)
    return key, f, (icon, m, src)


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


def main_v2(a):
    """Pre-fit v2 cameras for every donor (skips cached ones) so nightly generation only reads caches."""
    c = slopqueue.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    keys = a.only.split(",") if a.only else None
    summ_p = os.path.join(IF.CACHE, "_v2_summary.json")
    summ = json.load(open(summ_p)) if os.path.exists(summ_p) else {}
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        if keys and key not in keys:
            continue
        if os.path.exists(IF.cache_path(key, 2)):
            f = json.load(open(IF.cache_path(key, 2)))
        else:
            saved, ctx.fs = ctx.fs, d["fs"]
            try:
                f = fit_donor_v2(ctx, d, random.Random(7))[1]
            except Exception as e:
                print(key, "fit failed", repr(e)[:200])
                f = None
            finally:
                ctx.fs = saved
        summ[key] = dict(icon=(f or {}).get("icon_src"), scores=(f or {}).get("scores"), kind=(f or {}).get("model_kind"))
        json.dump(summ, open(summ_p, "w"), indent=1)
        print(key, summ[key], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--v2", action="store_true", help="v2: fit every donor's camera to its own icon (cached)")
    a = ap.parse_args()
    if a.v2:
        return main_v2(a)
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
