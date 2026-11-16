"""Before/after report for the attribute roller: N rolls with the old roller (v1, uniform over the
pool) and the relevance-aware roller (v2) on the SAME donors and classes, scored with the same
relevance tagger (relevance.py). Writes stats_report.json and stats_cards.png (6 v2 example cards).
Nothing is generated, published or applied.

  python -I statreport.py [--n 60] [--seed 7]
"""
import argparse
import collections
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pipeline as PL  # noqa: E402
import relevance  # noqa: E402
import attrdesc  # noqa: E402
import card  # noqa: E402
import slopqueue as Q  # noqa: E402
from generate import CLASSES  # noqa: E402
from PIL import Image  # noqa: E402


def score(ctx, attrs, prov, classes):
    by_name = {p["name"].lower(): p for p in ctx.pool}
    rows = []
    for a in attrs:
        p = by_name.get((a.get("base_def") or a["name"]).lower())
        if p is None:
            continue
        nd = relevance.needs(p, ctx.attr_cat)
        rows.append(dict(name=a["name"], cls=p["cls"], value=a["value"], needs=nd, relevant=nd in prov,
                         effect=p["effect"], visible=bool(not p["hidden"] and p.get("desc_text")),
                         flavour=relevance.flavour(p, classes)))
    n = len(rows) or 1
    return dict(attrs=rows, n=len(rows), relevant_share=sum(r["relevant"] for r in rows) / n,
                irrelevant=sum(not r["relevant"] for r in rows),
                upside=any(r["relevant"] and r["effect"] == "positive" and r["visible"] for r in rows),
                downside=any(r["relevant"] and r["effect"] == "negative" and r["visible"] for r in rows),
                flavour=sum(r["flavour"] and r["relevant"] for r in rows))


def summary(rolls):
    sh = [r["relevant_share"] for r in rolls]
    return dict(weapons=len(rolls), mean_relevant_share=round(statistics.mean(sh), 3),
                median_relevant_share=round(statistics.median(sh), 3),
                weapons_at_least_85pct_relevant=sum(s >= 0.85 for s in sh),
                weapons_all_relevant=sum(s == 1 for s in sh),
                weapons_with_irrelevant=collections.Counter(min(r["irrelevant"], 3) for r in rolls),
                with_meaningful_upside=sum(r["upside"] for r in rolls),
                with_meaningful_downside=sum(r["downside"] for r in rolls),
                with_class_flavour=sum(r["flavour"] > 0 for r in rolls),
                mean_attrs=round(statistics.mean(r["n"] for r in rolls), 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    c = Q.cfg()
    ctx = PL.Ctx(c)
    rng = random.Random(a.seed)
    before, after, cards = [], [], []
    for i in range(a.n):
        d = rng.choice(ctx.donors)
        home = [x for x in d["classes"] if x in CLASSES] or ["Soldier"]
        classes = [rng.choice(home)]
        ic = d["kv"].get("item_class")
        prov = relevance.provides(ic, d["fam"], classes, d["slot"])
        r1 = PL.roll_attributes(ctx, random.Random(a.seed * 1000 + i), d["fam"], d["slot"], {"algo": "v1"}, ic, classes)
        r2 = PL.roll_attributes(ctx, random.Random(a.seed * 1000 + i), d["fam"], d["slot"], {}, ic, classes)
        s1, s2 = score(ctx, r1, prov, classes), score(ctx, r2, prov, classes)
        base = dict(donor="%s:%s" % (d["src"], d["id"]), item_class=ic, family=d["fam"], classes=classes)
        before.append(dict(base, **s1))
        after.append(dict(base, **s2))
        if len(cards) < 6 and classes[0] not in {x[1] for x in cards}:
            cards.append((r2, classes[0], ic, d))
    imgs = []
    for k, (attrs, cls, ic, d) in enumerate(cards):
        lines = attrdesc.sort_lines(attrdesc.item_lines([(x["name"], x["value"]) for x in attrs], ctx.defs, ctx.L))
        itn = ctx.stock_types.get(ic) or PL.TYPE_NAMES.get(ic, ic)
        typ = ctx.tf2c_tokens.get(itn[1:].lower(), itn) if itn.startswith("#") else itn
        name = "Example %d (%s)" % (k + 1, cls)
        imgs.append(card.render_card(name, "Level %d %s" % (random.Random(k).randint(1, 100), typ), lines, None, fonts=ctx.fonts))
    if imgs:
        w = max(i.width for i in imgs)
        cols = 2
        rows = (len(imgs) + 1) // 2
        hs = [max(imgs[r * cols + cc].height for cc in range(cols) if r * cols + cc < len(imgs)) for r in range(rows)]
        sheet = Image.new("RGBA", (w * cols + 20, sum(hs) + 10 * (rows + 1)), (20, 20, 20, 255))
        y = 10
        for r in range(rows):
            for cc in range(cols):
                if r * cols + cc < len(imgs):
                    sheet.paste(imgs[r * cols + cc], (cc * (w + 10) + 5, y))
            y += hs[r] + 10
        sheet.save(os.path.join(ROOT, "stats_cards.png"))
    rep = dict(n=a.n, seed=a.seed, before=summary(before), after=summary(after),
               examples=[dict(classes=[x[1]], item_class=x[2], donor="%s:%s" % (x[3]["src"], x[3]["id"]),
                              attrs=[dict(name=t["name"], value=t["value"], needs=t.get("needs"), relevant=t.get("relevant"))
                                     for t in x[0]]) for x in cards],
               rolls_before=before, rolls_after=after)
    json.dump(rep, open(os.path.join(ROOT, "stats_report.json"), "w"), indent=1, default=str)
    print(json.dumps(dict(before=rep["before"], after=rep["after"]), indent=1, default=str))


if __name__ == "__main__":
    main()
