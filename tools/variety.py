"""Variety sheet: one donor (TF2C scattergun) with 8 whacky deformations + in-hand renders.
Outputs proto/render/variety_scattergun.png and variety_scattergun_viewmodel.png."""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mutate  # noqa: E402
import pipeline  # noqa: E402
import slopqueue  # noqa: E402
import srcmodel as S  # noqa: E402
import vmrender  # noqa: E402

V = {"droopy": dict(droop=0.35, pivot=0.35), "twisted": dict(twist=140, pivot=0.35),
     "bent up": dict(bend=-35, bend_plane=90, pivot=0.4), "blunderbuss": dict(flare=2.4, pivot=0.4),
     "distended barrel": dict(bulge=1.3, bulge_at=0.78, bulge_width=0.1), "squashed": dict(squash=2.1, pivot=0.35),
     "wobbly": dict(wobble=0.035, wobble_freq=3, pivot=0.3),
     "combo": dict(droop=0.22, twist=50, flare=1.6, stretch=1.4, pivot=0.4)}


def main():
    c = slopqueue.cfg()
    c["_attr_registry"] = {}
    ctx = pipeline.Ctx(c)
    tmp = os.path.join(ROOT, "tmp", "var2")
    w = pipeline.extract_model(ctx, "models/weapons/w_models/w_scattergun.mdl", os.path.join(tmp, "src"))
    v = pipeline.extract_model(ctx, "models/weapons/v_models/v_scattergun_scout.mdl", os.path.join(tmp, "src"))
    tiles = [("stock", pipeline.render_with_fs(ctx, S.load(w), None))]
    vms = [("stock", v)]
    for k, p in V.items():
        n = k.replace(" ", "_")
        r = mutate.mutate(w, tmp, "models/customslop/var/w_%s.mdl" % n, "models/customslop/var", p)
        tiles.append(("%s (coarse parts %d)" % (k, r["coarse_parts"]),
                      pipeline.render_with_fs(ctx, S.load(os.path.join(tmp, "models/customslop/var/w_%s.mdl" % n)), None)))
        if k in ("droopy", "blunderbuss", "combo"):
            mutate.mutate(v, tmp, "models/customslop/var/v_%s.mdl" % n, "models/customslop/var", p)
            vms.append((k, os.path.join(tmp, "models/customslop/var/v_%s.mdl" % n)))
    T = 340
    sh = Image.new("RGBA", (T * 3, (T + 20) * 3), (60, 60, 60, 255))
    d = ImageDraw.Draw(sh)
    for i, (k, im) in enumerate(tiles):
        x, y = (i % 3) * T, (i // 3) * (T + 20)
        sh.alpha_composite(im.resize((T, T)), (x, y + 20))
        d.text((x + 8, y + 4), k, fill=(255, 255, 255))
    sh.save(os.path.join(ROOT, "proto", "render", "variety_scattergun.png"))
    rows = []
    for k, p in vms:
        im, rep = vmrender.render_viewmodel(ctx, p, "models/weapons/c_models/c_scout_arms.mdl", size=(640, 360))
        rows.append((k, im, rep))
    vs = Image.new("RGB", (1280, 380 * len(rows)), (60, 60, 60))
    d = ImageDraw.Draw(vs)
    for i, (k, im, rep) in enumerate(rows):
        vs.paste(im, (0, i * 380 + 20))
        d.text((8, i * 380 + 4), "%s - first person | side view (idle pose, Scout arms bonemerged: %s)"
               % (k, "ok" if rep and rep["ok"] else rep), fill=(255, 255, 255))
    vs.save(os.path.join(ROOT, "proto", "render", "variety_scattergun_viewmodel.png"))
    print([(k, r) for k, _, r in rows])


if __name__ == "__main__":
    main()
