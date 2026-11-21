"""Strip persisting (player-scoped) and no-effect attributes from CustomSlop's own catalogued
weapons in place (same defindex, same assets), per tools/attrscope.py. If a weapon is left without
a meaningful upside or downside, one working weapon-/active-scoped attribute of the missing sign
is added from its item class's validated pool (deterministic per defindex, mild value).
--effect (user 2026-11-20, "make sure every attribute applied actually works"): also enforce the
reviewed effect table tools/attreffect.py - stats not on it (or not applying to the item class) are
removed, values outside the reviewed range are clamped into it (re-rolled when on the wrong side,
e.g. "deploys slower" at 0.7), a missing upside/downside is refilled only from the table.
Backups: item.txt.pre_strip / .pre_effect, card.png.pre_strip / .pre_effect. Journal: "strip_attrs"
or "effect_fix". The card is re-rendered
only if a stat line changed. Touches only queue/<...>/<id>/ of catalogued live/approved weapons.

  python -I strip_attrs.py [--ids 26035 ...] [--dry-run] [--effect]
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
import attreffect as E  # noqa: E402
import pipeline as P  # noqa: E402
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402


def pool_entry(ctx, name):
    by = {p["name"].lower(): p for p in ctx.pool}
    n = name.lower()
    return by.get(n) or by.get(n.replace("customslop ", "", 1))


def in_range(p, v, rng):
    """(value, how) inside the reviewed range: kept / clamped / re-rolled."""
    sp = E.SPEC.get(p["name"])
    if not sp or not sp["v"]:
        return v, "kept"
    lo, hi = min(sp["v"]), max(sp["v"])
    if lo <= v <= hi:
        return v, "kept"
    mult = p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage")
    pivot = 1.0 if mult and lo > 0 else 0.0
    same_side = (v - pivot) * (lo - pivot) > 0 and (v - pivot) * (hi - pivot) > 0
    if same_side:
        # live weapons: only a value too WEAK to notice is raised to the range's weak end; a stronger
        # working value stays (no unrequested nerfs: user rule, weapons change only where broken)
        weak = lo if abs(lo - pivot) < abs(hi - pivot) else hi
        if abs(v - pivot) >= abs(weak - pivot):
            return v, "kept"
        return weak, "raised"
    return E.roll(p, rng), "re-rolled"


def strip_one(ctx, w, cl, ln, dry, effect=False):
    d = os.path.join(ROOT, w["dir"])
    path = os.path.join(d, "item.txt")
    old = open(path, encoding="utf-8").read()
    key, it = kv.parse(old)[0].pairs[0]
    ic = it.get("item_class")
    at = it.get("attributes")
    before = [(n, b.get("attribute_class"), b.get("value")) for n, b in at.blocks()]
    keep, removed, fixed = [], [], []
    rng0 = random.Random(int(key) * 7 + 1)
    for n, b in at.blocks():
        info = cl.get(b.get("attribute_class"))
        ok_ = A.works_on(info, ic, ln)
        p = pool_entry(ctx, n)
        if ok_ and effect:
            if p is None or p.get("vscript"):
                ok_ = bool(p and p.get("vscript"))
            elif p["name"] in E.DROPPED or (p["name"] in E.SPEC and not E.allowed(p, ic)):
                ok_ = False                   # reviewed: does nothing / wrong text / not for this item class
            elif p["name"] not in E.SPEC:
                # unreviewed: a visible line could read wrong -> remove; an invisible multiplier that
                # really changes something (e.g. hidden +81% damage) stays, anything else goes
                try:
                    vv = float(b.get("value"))
                except (TypeError, ValueError):
                    vv = None
                ok_ = bool((p.get("hidden") or not p.get("desc_text")) and vv is not None
                           and p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage")
                           and abs(vv - 1.0) >= 0.05)
            else:
                ok_ = True                    # pool_entry maps "customslop <def>" re-declarations to <def>
                if ok_:
                    try:
                        v0 = float(b.get("value"))
                    except (TypeError, ValueError):
                        v0 = None
                    if v0 is not None:
                        v1, how = in_range(p, v0, rng0)
                        if how != "kept":
                            nb = kv.KV([(k_, str(v1) if k_ == "value" else v_) for k_, v_ in b.pairs])
                            fixed.append((n, b.get("attribute_class"), v0, v1, how))
                            b = nb
        (keep if ok_ else removed).append((n, b))
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
                 and A.works_on(cl.get(p["cls"]), ic, ln) and P.relevance.needs(p, ctx.attr_cat) in prov
                 and (not effect or E.allowed(p, ic))]
        if not cands:
            continue
        ncls = {}
        for p in cands:
            ncls[p["cls"]] = ncls.get(p["cls"], 0) + 1
        wts = [1.0 / ncls[p["cls"]] for p in cands]       # uniform over attribute classes (standing rule 2026-11-20)
        out = None
        for _ in range(30):
            p = cands[int(rng.choices(range(len(cands)), weights=wts)[0])]
            v = E.roll(p, rng) if effect else None
            if v is None:
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
    if not removed and not added and not fixed:
        return dict(defindex=int(key), item_class=ic, changed=False, attributes=before)
    na = kv.KV()
    for n, b in keep:
        na.add(n, b)
    it = kv.KV([(k, na if k == "attributes" else v) for k, v in it.pairs])
    new = '"%s"\n{\n%s}\n' % (key, kv.dump(it, 1))
    res = dict(defindex=int(key), item_class=ic, changed=True, before=before,
               removed=[(n, b.get("attribute_class")) for n, b in removed], added=added, fixed=fixed,
               after=[(n, b.get("attribute_class"), b.get("value")) for n, b in keep])
    if dry:
        return res
    bak = ".pre_effect" if effect else ".pre_strip"
    if not os.path.exists(path + bak):
        shutil.copyfile(path, path + bak)
    open(path, "w", encoding="utf-8", newline="\n").write(new)
    # card: re-render only if a stat line changed (always the case here)
    cp = os.path.join(d, "card.png")
    if os.path.exists(cp):
        if not os.path.exists(cp + bak):
            shutil.copyfile(cp, cp + bak)
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
    ap.add_argument("--effect", action="store_true", help="also enforce the reviewed effect table (attreffect.py)")
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
        out.append(strip_one(ctx, w, cl, ln, a.dry_run, a.effect))
    changed = [r["defindex"] for r in out if r["changed"]]
    if changed and not a.dry_run:
        Q.journal(st, "effect_fix" if a.effect else "strip_attrs", ids=changed,
                  removed={r["defindex"]: [x[1] for x in r["removed"]] for r in out if r["changed"]},
                  added={r["defindex"]: [x[1] for x in r["added"]] for r in out if r["changed"]},
                  fixed={r["defindex"]: [[x[0], x[2], x[3]] for x in r.get("fixed", [])] for r in out if r["changed"]})
        Q.save_state(st)
    json.dump(out, open(os.path.join(ROOT, "%s_result%s.json" % ("effect_fix" if a.effect else "strip_attrs",
                                                                  "_dryrun" if a.dry_run else "")), "w"),
              indent=1, default=str)
    for r in out:
        print(json.dumps(r, default=str))


if __name__ == "__main__":
    main()
