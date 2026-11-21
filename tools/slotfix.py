"""Fix catalogued CustomSlop weapons that break the slot rule (slotrule.py; user bug 2026-11-20:
"customslop weapons preventing slot 1/2 picking") with the smallest change, in place (same
defindex, model, name, assets):
  1. move: if the item_class is natively in ONE common slot for all its classes (and they can taunt
     with it), give it that slot - item_class and stats unchanged (e.g. a Sniper SMG in primary
     -> secondary);
  2. swap: else an item_class native to the given slot for every class, same family, taunt-capable
     (slotrule.fix) - stats whose source scope no longer reads them for the new class are dropped;
  3. narrow: else keep only the classes that pass 1. or 2. on their own (the first that does).
Backups item.txt.pre_slot / summary.json.pre_slot (card.png.pre_slot when a stat line changed).
Journal "slotfix". Touches only queue/<...>/<id>/ of catalogued live/approved weapons.

  python -I slotfix.py [--ids ...] [--dry-run]
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pipeline as P  # noqa: E402
import attrscope as A  # noqa: E402
import attreffect as E  # noqa: E402
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402
import slotrule  # noqa: E402
import taunts  # noqa: E402
import strip_attrs as SA  # noqa: E402


def plan(fs, ic, slot, ubc, fam):
    eff = {c: slotrule.slot_for(ubc, c, slot) for c in ubc}
    if all(slotrule.ok(c, ic, s) for c, s in eff.items()):
        return None
    # 1. move to a common native slot
    common = None
    for s in slotrule.SLOTS:
        if all(slotrule.ok(c, ic, s) and taunts.ok(fs, c, ic) for c in ubc):
            common = s
            break
    if common:
        return dict(how="move", item_class=ic, slot=common, classes={c: "1" for c in ubc})
    # 2. swap item_class, same slots
    nic = slotrule.fix(fs, eff, ic, fam)
    if nic:
        return dict(how="swap", item_class=nic, slot=slot, classes=dict(ubc))
    # 3. narrow to one class that passes alone (move first, then swap)
    subs = [(c, plan(fs, ic, slot, {c: ubc[c]}, fam)) for c in ubc]
    subs = [(c, x) for c, x in subs if x is not None and x["how"] != "none"]
    subs.sort(key=lambda cx: cx[1]["how"] != "move")     # keeping the item_class beats swapping it
    if subs:
        c, sub = subs[0]
        return dict(sub, how="narrow+" + sub["how"], dropped=[x for x in ubc if x != c])
    return dict(how="none")


def fix_one(ctx, w, cl, ln, dry):
    d = os.path.join(ROOT, w["dir"])
    path = os.path.join(d, "item.txt")
    old = open(path, encoding="utf-8").read()
    key, it = kv.parse(old)[0].pairs[0]
    ic, slot = it.get("item_class"), it.get("item_slot")
    ubc = dict(it.get("used_by_classes").pairs)
    summ = json.load(open(os.path.join(d, "summary.json")))
    pl = plan(ctx.fs, ic, slot, ubc, summ.get("family"))
    if pl is None:
        return dict(defindex=int(key), changed=False)
    res = dict(defindex=int(key), changed=pl["how"] != "none", before=dict(item_class=ic, slot=slot, classes=ubc), plan=pl)
    if pl["how"] == "none":
        return res
    at = it.get("attributes")
    keep, dropped = [], []
    for n, b in (at.blocks() if at else []):
        info = cl.get(b.get("attribute_class"))
        p = SA.pool_entry(ctx, n)
        ok_ = A.works_on(info, pl["item_class"], ln) and (p is None or p["name"] not in E.SPEC or E.allowed(p, pl["item_class"]))
        (keep if ok_ else dropped).append((n, b))
    res["dropped_stats"] = [n for n, _ in dropped]
    if dry:
        return res
    nubc = kv.KV([(c, v) for c, v in pl["classes"].items()])
    na = kv.KV()
    for n, b in keep:
        na.add(n, b)
    pairs = []
    for k_, v_ in it.pairs:
        if k_ == "item_class":
            v_ = pl["item_class"]
        elif k_ == "item_slot":
            v_ = pl["slot"]
        elif k_ == "used_by_classes":
            v_ = nubc
        elif k_ == "attributes":
            v_ = na
        pairs.append((k_, v_))
    it2 = kv.KV(pairs)
    for f in ("item.txt", "summary.json"):
        if not os.path.exists(os.path.join(d, f + ".pre_slot")):
            shutil.copyfile(os.path.join(d, f), os.path.join(d, f + ".pre_slot"))
    open(path, "w", encoding="utf-8", newline="\n").write('"%s"\n{\n%s}\n' % (key, kv.dump(it2, 1)))
    summ["item_class"] = pl["item_class"]
    summ["slot"] = pl["slot"]
    summ["classes"] = pl["classes"]
    summ["slot_native"] = {c: slotrule.ok(c, pl["item_class"], slotrule.slot_for(pl["classes"], c, pl["slot"]))
                           for c in pl["classes"]}
    summ["taunt"] = {c: taunts.ok(ctx.fs, c, pl["item_class"]) for c in pl["classes"]}
    json.dump(summ, open(os.path.join(d, "summary.json"), "w"), indent=1)
    if dropped:
        cp = os.path.join(d, "card.png")
        if os.path.exists(cp):
            if not os.path.exists(cp + ".pre_slot"):
                shutil.copyfile(cp, cp + ".pre_slot")
            from PIL import Image
            lines = P.attrdesc.sort_lines(P.attrdesc.item_lines([(n, b.get("value")) for n, b in keep], ctx.defs, ctx.L))
            lines.append((it2.get("item_description") or "", "neutral"))
            icon = Image.open(os.path.join(d, "icon.png")) if os.path.exists(os.path.join(d, "icon.png")) else None
            P.card.render_card(it2.get("item_name"), summ.get("type_line", ""), lines, icon, fonts=ctx.fonts,
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
        if w.get("slotfix_exempt"):                       # user: "leave the AR in primary" (26061)
            out.append(dict(defindex=int(k), changed=False, exempt=True))
            continue
        out.append(fix_one(ctx, w, cl, ln, a.dry_run))
    changed = [r for r in out if r.get("changed")]
    if changed and not a.dry_run:
        for r in changed:                                 # catalogue mirror of the item's classes / slot
            w = st["weapons"][str(r["defindex"])]
            w["classes"] = list(r["plan"]["classes"])
            w["slot"] = r["plan"]["slot"]
        Q.journal(st, "slotfix", ids=[r["defindex"] for r in changed],
                  changes={r["defindex"]: dict(how=r["plan"]["how"], item_class=r["plan"]["item_class"],
                                               slot=r["plan"]["slot"], classes=list(r["plan"]["classes"]),
                                               dropped_stats=r.get("dropped_stats", [])) for r in changed})
        Q.save_state(st)
    json.dump(out, open(os.path.join(ROOT, "slotfix_result%s.json" % ("_dryrun" if a.dry_run else "")), "w"), indent=1)
    for r in out:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
