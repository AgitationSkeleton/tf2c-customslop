"""Side-profile camera fit for donor icons (user: "couldn't even tell the Telepro Plus was the
assault rifle because of the terrible camera angle"; renders must resemble the donor's original
bucket/backpack icon). Unlike the free v3 search, every candidate camera is built from the model's
own axes as a SIDE view: the long (barrel) axis lies in the image plane and the view direction is
one of the two other principal axes, both signs, both barrel directions, mirrored or not. Each
candidate is then refined with a bounded tilt (view direction within 35 deg of the side view, any
in-plane roll; at most a 3/4 view: |view . barrel| <= 0.8, like the stock icons' ~0.6-0.7) and perspective, scored by silhouette IoU against the source icon, and the best are
re-ranked by colour agreement. End-on and top-down views cannot result.

  fit:    python -I side_fit.py fit [--only k,k] [--tag t]     -> tmp/side_fit_<t>.json
  merge:  python -I side_fit.py merge                           -> tools/icon_overrides.json entries,
          cache/icon_fit/<key>_v3.json for donors whose side camera wins, icon_overrides_review.png
A donor's side camera replaces its current v3 camera when it scores higher (canvas IoU + 0.5 x
colour correlation), or always when the current camera looks along the barrel (|view . barrel| > 0.85).
Read-only on state/ and queue/.
"""
import argparse
import glob
import json
import math
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

OVR = os.path.join(HERE, "icon_overrides.json")


def load(ctx, d):
    key = "%s:%s" % (d["src"], d["id"])
    f3 = json.load(open(IF.cache_path(key, 3))) if os.path.exists(IF.cache_path(key, 3)) else {}
    kind = f3.get("model_kind", "w")
    rel = d["mp"] if kind == "v" or not d.get("mw") else d["mw"]
    saved, ctx.fs = ctx.fs, d["fs"]
    try:
        icon, why = fit_icons.source_icon(ctx, d)
        if icon is None:
            return None
        m = S.load(pipeline.extract_model(ctx, rel, tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))))
        if os.path.basename(rel).lower().startswith("v_"):
            m = IF.posed(m)
        tex = vmrender.textures_for(ctx, m, None)
        mats = vmrender.materials_for(ctx, m, None)
    finally:
        ctx.fs = saved
    return dict(key=key, f3=f3, kind=kind, rel=rel, icon=icon, why=why, m=m, tex=tex, mats=mats)


def axes(m):
    T = np.concatenate([t for _, t in IF.tri_list(m)])
    P = m.raw_pos
    area = np.linalg.norm(np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]), axis=1)
    cen = (P[T[:, 0]] + P[T[:, 1]] + P[T[:, 2]]) / 3
    pcs = np.linalg.svd(cen - np.average(cen, axis=0, weights=area), full_matrices=False)[2]
    a = pcs[0]
    b = pcs[1] if len(pcs) > 1 else np.cross(a, [0, 0, 1.0])
    c = np.cross(a, b)
    return T, area, a, b / np.linalg.norm(b), c / np.linalg.norm(c)


def colour_score(m, icon, R, mirror, D, tex, mats):
    ia = icon[..., 3].astype(np.float32) / 255
    ibb = IF.bbox(ia)
    pp = (D, float((m.raw_pos @ R.T)[:, 1].mean())) if D else None
    buf = IF.raster_buffers(m, R, 160, textures=tex, mirror=mirror, persp=pp)
    bb = IF.bbox(buf["alpha"])
    if bb is None:
        return 0.0
    col = SS.shade(buf["nrm"], buf["alb"], buf["balpha"], buf["uv"], buf["matid"], buf["alpha"], mats)
    rc = IF.crop_norm(col, bb)
    icol = IF.crop_norm(icon[..., :3].astype(np.float32) / 255, ibb)
    msk = (IF.crop_norm(ia, ibb) > 0.5) & (IF.crop_norm(buf["alpha"], bb) > 0.5)
    if msk.sum() < 40:
        return 0.0
    c = [np.corrcoef(rc[..., k][msk], icol[..., k][msk])[0, 1] for k in range(3)]
    return float(np.nanmean(c))


def fit_side(x, rng):
    m, icon = x["m"], x["icon"]
    T, area, a, b, c = axes(m)
    mid = T[np.argsort(-area)[:1500]]
    imask = IF.letterbox_mask(icon[..., 3] / 255.0)
    P = m.raw_pos
    ext = float(np.linalg.norm(P.max(0) - P.min(0)))

    def score(R, mirror, tris, D=None):
        Qp = P @ R.T
        if mirror:
            Qp[:, 0] *= -1
        if D:
            Qp = IF.persp_xform(Qp, (D, float(Qp[:, 1].mean())))
        return IF.iou(IF.silhouette(Qp[:, [0, 2]], tris), imask)
    ys, xs = np.nonzero(icon[..., 3] > 127)
    phi_i = IF._pca_angle(np.stack([xs, -ys], 1).astype(np.float64))
    cands = []
    for d in (b, -b, c, -c):
        for xa in (a, -a):
            xv = xa - (xa @ d) * d
            xv /= np.linalg.norm(xv)
            R0 = np.stack([xv, d, np.cross(xv, d)])
            for mirror in IF.mirrors():
                # start with the long axis at the icon's principal angle
                Qp = (P @ R0.T)[:, [0, 2]].copy()
                if mirror:
                    Qp[:, 0] *= -1
                phi_m = IF._pca_angle(Qp)
                for extra in (0.0, math.pi):
                    al = phi_i - phi_m + extra
                    beta = -al if mirror else al
                    R = IF._rot2(R0, -beta)
                    if abs(R[1] @ a) > 0.8:
                        continue
                    for D in (None, 1.3 * ext, 0.8 * ext):
                        cands.append((score(R, mirror, mid, D), R, mirror, D, R0[1]))
    cands.sort(key=lambda t: -t[0])
    out = []
    for s0, R, mirror, D, d0 in cands[:8]:
        cur, cs, cd = R, s0, D
        step = 0.25
        for it in range(70):
            ax = np.array([rng.gauss(0, 1) for _ in range(3)])
            tr = IF._axis_rot(ax, step) @ cur
            u, _, vt = np.linalg.svd(tr)
            tr = u @ vt
            if abs(tr[1] @ d0) < math.cos(math.radians(50)) or abs(tr[1] @ a) > 0.8:
                continue                     # stay a side view: never end-on, never top-down
            sc = score(tr, mirror, mid, cd)
            if sc > cs:
                cur, cs = tr, sc
            if it % 7 == 6 and cd:
                for k in (0.8, 1.25):
                    sd = score(cur, mirror, mid, cd * k)
                    if sd > cs:
                        cs, cd = sd, cd * k
            if it % 14 == 13:
                step *= 0.6
        full = score(cur, mirror, T, cd)
        out.append((full + 0.5 * colour_score(m, icon, cur, mirror, cd, x["tex"], x["mats"]), full, cur, mirror, cd))
    out.sort(key=lambda t: -t[0])
    return out[0], a


def fit_one(ctx, d, rng):
    x = load(ctx, d)
    if x is None:
        return None
    (tot, s_iou, R, mir, D), a = fit_side(x, rng)
    side = IF.fit_v2(x["m"], x["icon"], rng, icon_src=x["why"], textures=x["tex"], v3=True, mats=x["mats"],
                     override=dict(R=R.tolist(), mirror=bool(mir), persp_d=D, iou=s_iou))
    f3 = x["f3"]
    res = dict(key=x["key"], icon_src=x["why"], kind=x["kind"], side_iou=side["scores"]["iou_canvas"],
               side_R=R.tolist(), side_mirror=bool(mir), side_persp_d=D, v3_iou=(f3.get("scores") or {}).get("iou_canvas"))
    if f3.get("R"):
        R3 = np.array(f3["R"])
        res["v3_end_on"] = bool(abs(R3[1] @ a) > 0.85)
        D3 = f3["persp"][0] if f3.get("persp") else None
        res["v3_colour"] = colour_score(x["m"], x["icon"], R3, f3.get("mirror", False), D3, x["tex"], x["mats"])
    res["side_colour"] = colour_score(x["m"], x["icon"], R, mir, D, x["tex"], x["mats"])
    sv = res["side_iou"] + 0.5 * res["side_colour"]
    vv = (res["v3_iou"] or 0) + 0.5 * (res.get("v3_colour") or 0)
    res["choice"] = "side" if (res.get("v3_end_on") or not f3.get("R") or sv > vv + 0.01) else "v3"
    return res


def cmd_fit(a):
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    keys = a.only.split(",") if a.only else None
    outp = os.path.join(ROOT, "tmp", "side_fit_%s.json" % (a.tag or "all"))
    done = json.load(open(outp)) if os.path.exists(outp) else {}
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        if (keys and key not in keys) or key in done:
            continue
        try:
            r = fit_one(ctx, d, random.Random(11))
        except Exception as e:
            r = dict(key=key, error=repr(e)[:200])
        if r:
            done[key] = r
            json.dump(done, open(outp, "w"), indent=1, default=float)
            print(key, r.get("choice"), "v3 %s side %s" % (r.get("v3_iou"), r.get("side_iou")), flush=True)


def decide(r):
    """Side camera only if it is a real fit (IoU >= 0.45) and either the current camera looks along
    the barrel while matching its icon poorly (< 0.8), or the side camera matches clearly better
    (IoU + 0.5 x colour). A current camera that matches its (foreshortened) original icon well stays."""
    if not r.get("v3_iou"):
        return "side" if r["side_iou"] >= 0.45 else "v3"
    if r["side_iou"] < 0.45:
        return "v3"
    if r.get("v3_end_on") and r["v3_iou"] < 0.8:
        return "side"
    sv = r["side_iou"] + 0.5 * (r.get("side_colour") or 0)
    vv = r["v3_iou"] + 0.5 * (r.get("v3_colour") or 0)
    return "side" if sv > vv + 0.01 else "v3"


def cmd_merge(a):
    reject = set((a.reject or "").split(",")) - {""}
    res = {}
    for p in glob.glob(os.path.join(ROOT, "tmp", "side_fit_*.json")):
        res.update(json.load(open(p)))
    ovr = json.load(open(OVR)) if os.path.exists(OVR) else {}
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    rows = []
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        r = res.get(key)
        if not r or r.get("error") or (a.only and key not in a.only.split(",")):
            continue
        x = load(ctx, d)
        if x is None:
            continue
        cur = IF.render_icon(x["m"], x["tex"], x["f3"], mats=x["mats"]) if x["f3"].get("R") else None
        r["choice"] = decide(r)
        changed = r["choice"] == "side" and key not in reject
        if changed and a.dry:
            ov = dict(R=r["side_R"], mirror=r["side_mirror"], persp_d=r["side_persp_d"], iou=r["side_iou"])
            f = IF.fit_v2(x["m"], x["icon"], random.Random(7), icon_src=x["why"], textures=x["tex"], v3=True,
                          mats=x["mats"], override=ov)
            new = IF.render_icon(x["m"], x["tex"], f, mats=x["mats"])
        elif changed:
            ov = dict(R=r["side_R"], mirror=r["side_mirror"], persp_d=r["side_persp_d"], iou=r["side_iou"],
                      source="side_fit", note="side-profile camera matched to %s (IoU %s -> %s)" % (
                          r["icon_src"], r.get("v3_iou"), r["side_iou"]))
            ovr[key] = ov
            f = IF.fit_v2(x["m"], x["icon"], random.Random(7), icon_src=x["why"], textures=x["tex"], v3=True,
                          mats=x["mats"], override=ov)
            f.update(donor=key, model=x["rel"], model_kind=x["kind"], previous_v3_scores=x["f3"].get("scores"))
            json.dump(f, open(IF.cache_path(key, 3), "w"), indent=1, default=float)
            new = IF.render_icon(x["m"], x["tex"], f, mats=x["mats"])
        if not changed:
            new = cur
        rows.append((key, r, Image.fromarray(x["icon"], "RGBA"), cur, new, changed))
        print(key, "CHANGED" if changed else "kept", r.get("v3_iou"), "->", r["side_iou"] if changed else r.get("v3_iou"), flush=True)
    if not a.dry:
        json.dump(ovr, open(OVR, "w"), indent=1)
    T = 200
    sh = Image.new("RGBA", (3 * (T + 10) + 470, (T + 10) * len(rows) + 40), (40, 40, 40, 255))
    dr = ImageDraw.Draw(sh)
    dr.text((10, 10), "source icon | current (v3 auto) | proposed  - green = changed (override), grey = kept", fill=(255, 255, 255, 255))
    y = 34
    for key, r, ic, cur, new, changed in rows:
        for k, im in enumerate((ic, cur, new)):
            if im is None:
                continue
            bg = Image.new("RGBA", (T, T), (40, 40, 40, 255))
            bg.alpha_composite(im.convert("RGBA").resize((T, T), Image.LANCZOS))
            sh.paste(bg, (10 + k * (T + 10), y))
        tx = 10 + 3 * (T + 10)
        col = (140, 240, 140, 255) if changed else (190, 190, 190, 255)
        dr.text((tx, y + 4), key, fill=(255, 255, 255, 255))
        dr.text((tx, y + 24), "%s  IoU %s -> %s%s" % ("CHANGED" if changed else "kept", r.get("v3_iou"),
                                                     r["side_iou"] if changed else r.get("v3_iou"),
                                                     "  (v3 was end-on)" if r.get("v3_end_on") else ""), fill=col)
        dr.text((tx, y + 44), (r["icon_src"] or "")[:64], fill=(180, 180, 180, 255))
        y += T + 10
    sh.save(os.path.join(ROOT, "icon_overrides_review%s.png" % ("_dry" if a.dry else "")))
    summ = dict(donors=len(rows), changed=[k for k, r, *_rest in rows if r["choice"] == "side" and k not in reject],
                rejected=sorted(reject))
    json.dump(dict(summary=summ, results=res), open(os.path.join(ROOT, "icon_overrides_review.json"), "w"), indent=1, default=float)
    print(json.dumps(summ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fit", "merge"])
    ap.add_argument("--only")
    ap.add_argument("--tag")
    ap.add_argument("--dry", action="store_true", help="merge: review sheet only, write nothing")
    ap.add_argument("--reject", help="merge: donor keys whose side camera is vetoed after review")
    a = ap.parse_args()
    {"fit": cmd_fit, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    main()
