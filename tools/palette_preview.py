"""Palette v4 preview sheet: N donors (mixed slots) x K random schemes, plus the v2 look for
comparison. usage: palette_preview.py [out.png] [seed]"""
import os
import random
import shutil
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mutate as MU  # noqa: E402
import palette  # noqa: E402
import pipeline  # noqa: E402
import slopqueue  # noqa: E402
import srcmodel as S  # noqa: E402

V2 = dict(front=dict(kind="tint", rgb=[70, 75, 82], strength=0.68), body=dict(kind="tint", rgb=[25, 25, 28], strength=0.72),
          accent=dict(kind="tint", rgb=[225, 228, 235], strength=0.7), grip=dict(kind="keep"))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "proto", "render", "palette_v4_preview.png")
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 21
    rng = random.Random(seed)
    c = slopqueue.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    by = {}
    for d in ctx.donors:
        if d["mw"]:
            by.setdefault(d["slot"], []).append(d)
    donors = [d for sl in ("primary", "secondary", "melee") for d in rng.sample(by[sl], 3)]
    K, T = 5, 220
    sheet = Image.new("RGB", (T * (K + 2), (T + 16) * len(donors) + 20), (52, 52, 56))
    dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), "stock | v2 tint (old) | palette v4 x%d (seed %d)" % (K, seed), fill=(255, 255, 255))
    avoid = []
    for row, d in enumerate(donors):
        saved, ctx.fs = ctx.fs, d["fs"]
        work = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
        try:
            src = pipeline.extract_model(ctx, d["mw"], work)
            tiles = [pipeline.render_with_fs(ctx, S.load(src), None, v2=True)]
            row_hues = []
            for j, assign in enumerate([V2] + [None] * K):
                files = os.path.join(work, "f%d" % j)
                rel = "models/customslop/pv%d/w.mdl" % j
                MU.mutate(src, files, rel, "models/customslop/pv%d" % j, {})
                if assign is None:
                    assign, hues = palette.scheme(rng, avoid, row_hues)   # same donor: must differ
                    avoid = (avoid + hues)[-12:]
                    row_hues += hues[:1]
                m = S.load(os.path.join(files, rel))
                pipeline.recolour_regions(ctx, src, m, files, "models/customslop/pv%d" % j, assign, {})
                tiles.append(pipeline.render_with_fs(ctx, m, files, v2=True))
            y = 20 + row * (T + 16)
            dr.text((6, y), "%s %s:%s %s" % (d["slot"], d["src"], d["id"], d["kv"].get("item_class")), fill=(220, 220, 220))
            for i, im in enumerate(tiles):
                im = im.convert("RGBA").resize((T, T))
                sheet.paste(im, (i * T, y + 14), im)
            print(row, d["src"], d["id"], flush=True)
        finally:
            ctx.fs = saved
            shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
