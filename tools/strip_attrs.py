"""Strip persisting (player-scoped) and no-effect attributes from CustomSlop's own catalogued
weapons in place (same defindex, same assets), per tools/attrscope.py. If a weapon is left without
a meaningful upside or downside, one working weapon-/active-scoped attribute of the missing sign
is added from its item class's validated pool (deterministic per defindex, mild value).
Backups: item.txt.pre_strip, card.png.pre_strip. Journal: "strip_attrs". The card is re-rendered
only if a stat line changed. Touches only queue/<...>/<id>/ of catalogued live/approved weapons.

  python -I strip_attrs.py [--ids 26035 ...] [--dry-run]
"""
import argparse
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import attrscope as A  # noqa: E402
import pipeline as P  # noqa: E402
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402


def pool_entry(ctx, name):
    by = {p["name"].lower(): p for p in ctx.pool}
    n = name.lower()
    return by.get(n) or by.get(n.replace("customslop ", "", 1))


def strip_one(ctx, w, cl, ln, dry):
    d = os.path.join(ROOT, w["dir"])
    path = os.path.join(d, "item.txt")
    old = open(path, encoding="utf-8").read()
    key, it = kv.parse(old)[0].pairs[0]
    ic = it.get("item_class")
    at = it.get("attributes")
    before = [(n, b.get("attribute_class"), b.get("value")) for n, b in at.blocks()]
    keep, removed = [], []
    for n, b in at.blocks():
        info = cl.get(b.get("attribute_class"))
        (keep if A.works_on(info, ic, ln) else removed).append((n, b))
    eff = lambda n: (pool_entry(ctx, n) or {}).get("effect")            # noqa: E731
    vis = lambda p: not p["hidden"] and p.get("desc_text")              # noqa: E731
    have = {(pool_entry(ctx, n) or {}).get("effect") for n, _ in keep if pool_entry(ctx, n) and vis(pool_entry(ctx, n))}
    added = []
    rng = random.Random(int(key))
    classes = [c for c, _ in it.get("used_by_classes").pairs] if it.get("used_by_classes") else []
    used = {b.get("attribute_class") for _, b in keep}
    summ = json.load(open(os.path.join(d, "summary.json")))
    prov = P.relevance.provides(ic, summ.get("family"), classes, it.get("item_slot"))
    for sign in ("positive", "negative"):
        if sign in have:
            continue
        cands = [p for p in ctx.pool if p["effect"] == sign and vis(p) and p["cls"] not in used and not p.get("vscript")
                 and not p["name"].upper().startswith(("CARD:", "SET BONUS", "TF_", "CUSTOMSLOP "))
                 and A.works_on(cl.get(p["cls"]), ic, ln) and P.relevance.needs(p, ctx.attr_cat) in prov]
        if not cands:
            continue
        wts = [(4.0 if P.relevance.flavour(p, classes) else 1.0) * (4.0 if P.CORE.search(p["cls"]) else 1.0) for p in cands]
        out = None
        for _ in range(30):
            p = cands[int(rng.choices(range(len(cands)), weights=wts)[0])]
            v = P.roll_value(p, rng, mild=True)
            # never introduce a CustomSlop re-declared definition here (it must exist in the schema):
            # skip values whose TF2 text would read wrong with the stock definition
            if p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage") and P.semantic_side(p)                     and P.attrdesc.value_for(p["fmt"], v) < 0 and P.attrpool.MAGNITUDE_WORDS.search(p["desc_text"]):
                continue
            out = dict(name=p["name"], cls=p["cls"], value=v)
            break
        if out is None:
            continue
        b = kv.KV()
        b.add("attribute_class", out["cls"])
        b.add("value", str(out["value"]))
        keep.append((out["name"], b))
        used.add(p["cls"])
        added.append((out["name"], out["cls"], out["value"]))
    if not removed and not added:
        return dict(defindex=int(key), item_class=ic, changed=False, attributes=before)
    na = kv.KV()
    for n, b in keep:
        na.add(n, b)
    it = kv.KV([(k, na if k == "attributes" else v) for k, v in it.pairs])
    new = '"%s"\n{\n%s}\n' % (key, kv.dump(it, 1))
    res = dict(defindex=int(key), item_class=ic, changed=True, before=before,
               removed=[(n, b.get("attribute_class")) for n, b in removed], added=added,
               after=[(n, b.get("attribute_class"), b.get("value")) for n, b in keep])
    if dry:
        return res
    if not os.path.exists(path + ".pre_strip"):
        shutil.copyfile(path, path + ".pre_strip")
    open(path, "w", encoding="utf-8", newline="\n").write(new)
    # card: re-render only if a stat line changed (always the case here)
    cp = os.path.join(d, "card.png")
    if os.path.exists(cp):
        if not os.path.exists(cp + ".pre_strip"):
            shutil.copyfile(cp, cp + ".pre_strip")
        from PIL import Image
        summ = json.load(open(os.path.join(d, "summary.json")))
        lines = P.attrdesc.sort_lines(P.attrdesc.item_lines([(n, b.get("value")) for n, b in keep], ctx.defs, ctx.L))
        lines.append((it.get("item_description") or "", "neutral"))
        icon = Image.open(os.path.join(d, "icon.png")) if os.path.exists(os.path.join(d, "icon.png")) else None
        P.card.render_card(it.get("item_name"), summ.get("type_line", ""), lines, icon, fonts=ctx.fonts,
                           crisp=ctx.cfg.get("renderer") == "v2").save(cp)
        res["card"] = "re-rendered"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = Q.cfg()
    st = Q.load_state(c)
    c2 = dict(c)
    c2["_attr_registry"], c2["_used_hues"] = c.get("_attr_registry", {}), []
    ctx = P.Ctx(c2)
    cl, ln = A.load()
    out = []
    for k, w in sorted(st["weapons"].items()):
        if w["status"] not in ("live", "approved") or (a.ids and int(k) not in a.ids):
            continue
        out.append(strip_one(ctx, w, cl, ln, a.dry_run))
    changed = [r["defindex"] for r in out if r["changed"]]
    if changed and not a.dry_run:
        Q.journal(st, "strip_attrs", ids=changed,
                  removed={r["defindex"]: [x[1] for x in r["removed"]] for r in out if r["changed"]},
                  added={r["defindex"]: [x[1] for x in r["added"]] for r in out if r["changed"]})
        Q.save_state(st)
    json.dump(out, open(os.path.join(ROOT, "strip_attrs_result%s.json" % ("_dryrun" if a.dry_run else "")), "w"),
              indent=1, default=str)
    for r in out:
        print(json.dumps(r, default=str))


if __name__ == "__main__":
    main()
