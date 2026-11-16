"""Re-render live CustomSlop weapons' icons + cards with the v2 renderer FOR COMPARISON ONLY.
Their published files are never touched (new icons would need new paths): output goes to
tmp/rerender/<id>/ and a sheet rerender_live.png (old icon | new icon | old card | new card).

  python -I rerender_live.py [26035 26042 26051]
"""
import json
import os
import random
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import attrdesc  # noqa: E402
import card  # noqa: E402
import fit_icons  # noqa: E402
import iconfit as IF  # noqa: E402
import kv  # noqa: E402
import pipeline  # noqa: E402
import slopqueue as Q  # noqa: E402
import srcmodel as S  # noqa: E402
import srcshade as SS  # noqa: E402
import vmrender  # noqa: E402


def main():
    ids = [int(x) for x in sys.argv[1:]] or [26035, 26042, 26051]
    c = Q.cfg()
    ctx = pipeline.Ctx(c)
    st = Q.load_state(c)
    rows = []
    for i in ids:
        w = st["weapons"][str(i)]
        d_ = os.path.join(ROOT, w["dir"])
        summ = json.load(open(os.path.join(d_, "summary.json")))
        donor = next(x for x in ctx.donors if x["src"] == summ["base"]["src"] and x["id"] == summ["base"]["id"])
        files = os.path.join(d_, "files")
        saved, ctx.fs = ctx.fs, donor["fs"]
        try:
            cp = IF.cache_path("%s:%s" % (donor["src"], donor["id"]), 2)
            f = json.load(open(cp)) if os.path.exists(cp) else fit_icons.fit_donor_v2(ctx, donor, random.Random(7))[1]
            tag = "cs%d" % i
            mdir = os.path.join(files, "models", "customslop", tag)
            kind = (f or {}).get("model_kind", "w")
            mp = os.path.join(mdir, "%s_%s.mdl" % ("v" if kind == "v" else "w", tag))
            if not os.path.exists(mp):
                mp = os.path.join(mdir, "v_%s.mdl" % tag)
            m = S.load(mp)
            if os.path.basename(mp).startswith("v_"):
                m = IF.posed(m)
            tex = vmrender.textures_for(ctx, m, files)
            mats = vmrender.materials_for(ctx, m, files)
        finally:
            ctx.fs = saved
        if f:
            icon = IF.render_icon(m, tex, f, mats=mats)
        else:
            fs_ = IF.family_style(summ.get("family"))
            icon = IF.render_icon(m, tex, IF.default_style(m, fs_["light"] if fs_ else None), mats=mats)
        out = os.path.join(ROOT, "tmp", "rerender", str(i))
        os.makedirs(out, exist_ok=True)
        icon.save(os.path.join(out, "icon_v2.png"))
        Image.fromarray(SS.bleed_edges(SS.resize_premul(np.asarray(icon), (256, 256))), "RGBA").save(os.path.join(out, "icon_v2_256.png"))
        it = kv.parse(open(os.path.join(d_, "item.txt"), encoding="utf-8").read())[0].pairs[0][1]
        at = it.get("attributes")
        lines = attrdesc.sort_lines(attrdesc.item_lines([(n, b.get("value")) for n, b in at.blocks()], ctx.defs, ctx.L))
        lines.append((it.get("item_description") or "", "neutral"))
        itn = it.get("item_type_name") or ""
        typ = ctx.tf2c_tokens.get(itn[1:].lower(), itn) if itn.startswith("#") else itn
        lvl = re.search(r"Level (\d+)", summ.get("type_line", "")) if summ.get("type_line") else None
        type_line = ctx.L.get("#ItemTypeDesc").replace("%s1", lvl.group(1) if lvl else "1").replace("%s2", typ)
        cimg = card.render_card(it.get("item_name"), type_line, lines, icon, fonts=ctx.fonts, crisp=True)
        cimg.save(os.path.join(out, "card_v2.png"))
        rows.append((i, Image.open(os.path.join(d_, "icon.png")), icon, Image.open(os.path.join(d_, "card.png")), cimg,
                     (f or {}).get("icon_src")))
        print(i, "fit", (f or {}).get("icon_src"), (f or {}).get("scores"), "stats old", SS.stats(np.asarray(Image.open(os.path.join(d_, "icon.png")).convert("RGBA")))["sat"],
              "new", SS.stats(np.asarray(icon))["sat"])
    T, CW = 300, 520
    rimgs = []
    for i, oi, ni, oc, nc, src in rows:
        cards = [im.convert("RGBA").resize((CW, int(im.height * CW / im.width)), Image.LANCZOS) for im in (oc, nc)]
        h = max(T, max(c.height for c in cards))
        r = Image.new("RGBA", (2 * (T + 10) + 2 * (CW + 10) + 10, h + 20), (40, 40, 40, 255))
        x = 10
        for im in (oi, ni):
            bg = Image.new("RGBA", (T, T), (40, 40, 40, 255))
            bg.alpha_composite(im.convert("RGBA").resize((T, T), Image.LANCZOS))
            r.paste(bg, (x, 10))
            x += T + 10
        for c_ in cards:
            r.paste(c_, (x, 10))
            x += CW + 10
        rimgs.append(r)
    sh = Image.new("RGBA", (rimgs[0].width, sum(r.height for r in rimgs)), (40, 40, 40, 255))
    y = 0
    for r in rimgs:
        sh.paste(r, (0, y))
        y += r.height
    sh.save(os.path.join(ROOT, "rerender_live.png"))
    print("wrote rerender_live.png")


if __name__ == "__main__":
    main()
