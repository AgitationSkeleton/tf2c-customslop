"""v4 icon cameras: every donor's camera re-made against its ORIGINAL icon (user review of 43 render
problems in the maintainer's icon review), with:
  * no mirroring (iconfit.ALLOW_MIRROR = False): a mirrored render shows a model that does not exist;
  * the reviewed per-donor specs (tools/icon_donors.json): the right reference icon (its own TF2C /
    tf2cc / Open Fortress icon, red team), view model + class arms, hidden shells, upright poses,
    and final turn180 / roll / explicit camera corrections;
  * Open Fortress donors framed on tf2cc's 512 px TF2C-convention copy of their bucket icon;
  * the renderer fixes (iconfit/srcshade/vmrender): back-face culling, $alphatest, $translucent glass,
    $basetexture with/without quotes or .vtf (no more "UV only" untextured renders).
Modes per donor:
  carry  - the v3 camera was not mirrored and the donor is not under review: same rotation, framed on
           the (possibly new) reference icon;
  refit  - mirrored v3 camera, a spec entry, or --refit: side-profile search (side_fit.fit_side) +
           the v3 camera's un-mirrored twin (M.R.S, S = reflection across the model's sagittal plane)
           refined locally, best of both by full-mesh IoU + 0.5 x colour agreement;
  upright- spec "upright": the model's own up axis stays vertical (yaw/pitch search only).
Writes cache/icon_fit/<key>_v4.json. Read-only on state/ and queue/.

  python -I fit_v4.py [--only k,k] [--refit k,k|all] [--skip-done]
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fit_icons  # noqa: E402
import iconfit as IF  # noqa: E402
import iconrig  # noqa: E402
import pipeline  # noqa: E402
import side_fit  # noqa: E402
import slopqueue as Q  # noqa: E402

VERSION = 4
IF.ALLOW_MIRROR = False
fit_icons.V4_TF2CC_FIRST = True


def model_for(ctx, d, kind, spec):
    rel = d["mp"] if kind == "v" or not d.get("mw") else d["mw"]
    f = dict(model_kind=kind, model=rel, arms=spec.get("arms"), hide=spec.get("hide"),
             bind_pose=spec.get("bind_pose"), squeeze=spec.get("squeeze"))
    m, tex, mats = iconrig.load_icon_model(ctx, d, f)
    m, tex, mats = iconrig.apply(m, tex, mats, f)
    return dict(m=m, tex=tex, mats=mats, rel=rel, kind=kind)


def score_full(x, icon, R, D):
    T = np.concatenate([t for _, t in IF.tri_list(x["m"])])
    imask = IF.letterbox_mask(icon[..., 3] / 255.0)
    Qp = x["m"].raw_pos @ R.T
    if D:
        Qp = IF.persp_xform(Qp, (D, float(Qp[:, 1].mean())))
    s = IF.iou(IF.silhouette(Qp[:, [0, 2]], T), imask)
    return s + 0.5 * side_fit.colour_score(x["m"], icon, R, False, D, x["tex"], x["mats"]), s


def refine(x, icon, R, D, rng, iters=60, bound=None):
    """Local random rotation search on the silhouette IoU (mid-size triangles), no mirror."""
    m = x["m"]
    T, area, a, b, c = side_fit.axes(m)
    mid = T[np.argsort(-area)[:1500]]
    imask = IF.letterbox_mask(icon[..., 3] / 255.0)
    P = m.raw_pos

    def sc(R_, D_):
        Qp = P @ R_.T
        if D_:
            Qp = IF.persp_xform(Qp, (D_, float(Qp[:, 1].mean())))
        return IF.iou(IF.silhouette(Qp[:, [0, 2]], mid), imask)
    cur, cs, cd = R, sc(R, D), D
    step = 0.2
    for it in range(iters):
        ax = np.array([rng.gauss(0, 1) for _ in range(3)])
        tr = IF._axis_rot(ax, step) @ cur
        u, _, vt = np.linalg.svd(tr)
        tr = u @ vt
        if bound and not bound(tr):
            continue
        s = sc(tr, cd)
        if s > cs:
            cur, cs = tr, s
        if it % 7 == 6 and cd:
            for k in (0.8, 1.25):
                sd = sc(cur, cd * k)
                if sd > cs:
                    cs, cd = sd, cd * k
        if it % 15 == 14:
            step *= 0.6
    return cur, cd


def unmirrored_twin(m, R):
    """Rotation showing (almost) the image a mirrored camera R showed, without mirroring: for a model
    symmetric across its sagittal plane (normal = thinnest principal axis n), M.R.S is a rotation."""
    _, _, a, b, c = side_fit.axes(m)
    n = c
    S = np.eye(3) - 2 * np.outer(n, n)
    M = np.diag([-1.0, 1.0, 1.0])
    R2 = M @ np.asarray(R) @ S
    u, _, vt = np.linalg.svd(R2)
    return u @ vt


def upright_search(x, icon, rng):
    """Model up (+z) stays screen-up: yaw sweep x small pitch, then a bounded refine."""
    best = None
    for yaw in range(0, 360, 10):
        for pitch in (-15, 0, 15, 30):
            R = IF.rot(yaw, 0, pitch)          # rot(yaw, roll-in-plane, pitch-about-screen-x)
            for D in (None,):
                t, s = score_full(x, icon, R, D)
                if best is None or t > best[0]:
                    best = (t, s, R, D)
    up_ok = lambda R_: R_[2][2] > 0.85                       # noqa: E731  model up stays near screen up
    R, D = refine(x, icon, best[2], best[3], rng, iters=40, bound=up_ok)
    return R, D


def fit_donor(ctx, d, rng, refit=False):
    key = "%s:%s" % (d["src"], d["id"])
    spec = fit_icons.donor_spec(key)
    icon, why = fit_icons.source_icon(ctx, d)
    if icon is None:
        return None
    f3p = IF.cache_path(key, 3)
    f3 = json.load(open(f3p)) if os.path.exists(f3p) else {}
    kinds = [spec["model_kind"]] if spec.get("model_kind") else (
        [f3.get("model_kind", "w")] if f3.get("model_kind") else ["w"])
    if spec.get("arms") and "v" not in kinds:
        kinds = ["v"]
    mode = "carry"
    if refit or spec or f3.get("mirror") or not f3.get("R"):
        mode = "refit"
    if spec.get("upright"):
        mode = "upright"
    best = None
    for kind in kinds:
        if kind == "w" and not (d.get("mw") or d.get("mp")):
            continue
        x = model_for(ctx, d, kind, spec)
        cands = []
        if f3.get("R") and f3.get("model_kind", "w") == kind:
            R3 = np.array(f3["R"])
            D3 = f3["persp"][0] if f3.get("persp") else None
            if f3.get("mirror"):
                R3 = unmirrored_twin(x["m"], R3)
                cands.append(("v3-twin", R3, D3))
                cands.append(("v3-twin180", np.diag([-1.0, -1.0, 1.0]) @ R3, D3))
            else:
                cands.append(("v3", R3, D3))
        if spec.get("R"):                       # reviewed explicit camera: no search
            Rr = np.array(spec["R"], float)
            cands = [("reviewed", Rr, spec.get("persp_d"))]
            if spec.get("refine"):
                # silhouette refinement that stays within ~35 deg of the reviewed camera
                near = lambda R_: np.trace(R_ @ Rr.T) > 1 + 2 * math.cos(math.radians(35))  # noqa: E731
                cands.append(("reviewed+refined", *refine(x, icon, Rr, spec.get("persp_d"), rng, iters=120, bound=near)))
        elif mode == "upright":
            R, D = upright_search(x, icon, rng)
            cands = [("upright", R, D)]
        elif mode == "refit":
            (tot, s_iou, R, mir, D), _a = side_fit.fit_side(dict(m=x["m"], icon=icon, tex=x["tex"], mats=x["mats"]), rng)
            cands.append(("side", R, D))
            if spec.get("free"):
                # prior-free dense search (any view direction): fists / arms / syringe rings, whose
                # original icons are not a side view of the long axis
                _s, Rf, _mi, Df = IF.fit_pose(x["m"], icon, rng, textures=x["tex"], v3=True, mats=x["mats"], hard=True)
                cands.append(("free", Rf, Df))
            cands = [(n_, *refine(x, icon, R_, D_, rng)) if n_.startswith("v3-twin") else (n_, R_, D_)
                     for n_, R_, D_ in cands]
        for name, R, D in cands:
            t, s = score_full(x, icon, R, D)
            if best is None or t > best[0]:
                best = (t, s, name, R, D, x)
    if best is None:
        return None
    t, s, name, R, D, x = best
    # explicit reviewed corrections on top (turn180 / roll / a full camera)
    ov = {k: spec[k] for k in ("turn180", "roll_deg") if k in spec}
    if ov and not spec.get("R"):
        R = np.array(IF.apply_override(dict(R=R.tolist(), mirror=False), ov)["R"])
    f = IF.fit_v2(x["m"], icon, rng, icon_src=why, textures=x["tex"], v3=True, mats=x["mats"],
                  override=dict(R=R.tolist(), mirror=False, persp_d=D, iou=s))
    f.update(version=VERSION, donor=key, model=x["rel"], model_kind=x["kind"], mode=mode, choice=name,
             arms=spec.get("arms"), hide=spec.get("hide"), upright=bool(spec.get("upright")),
             bind_pose=spec.get("bind_pose"), squeeze=spec.get("squeeze"),
             spec_note=spec.get("note"), v3_scores=f3.get("scores"), v3_mirror=bool(f3.get("mirror")))
    f["override"] = None
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--refit", help="donor keys to re-search even if their v3 camera is fine, or 'all'")
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    only = set(a.only.split(",")) if a.only else None
    refit = set((a.refit or "").split(",")) - {""}
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        if only and key not in only:
            continue
        if a.skip_done and os.path.exists(IF.cache_path(key, VERSION)):
            continue
        saved, ctx.fs = ctx.fs, d["fs"]
        try:
            f = fit_donor(ctx, d, random.Random(11), refit=("all" in refit or key in refit))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(key, "FAILED", repr(e)[:200], flush=True)
            continue
        finally:
            ctx.fs = saved
        if f is None:
            print(key, "no reference icon", flush=True)
            continue
        json.dump(f, open(IF.cache_path(key, VERSION), "w"), indent=1, default=float)
        print(key, f["mode"], f["choice"], f["scores"], f["icon_src"], flush=True)


if __name__ == "__main__":
    main()
