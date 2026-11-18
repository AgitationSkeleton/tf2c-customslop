"""Re-label CustomSlop's OWN catalogued items in place (same defindex, same assets): TF2C-localised
item_type_name and no Merc / tf2cc-only keys on non-Merc items (labels.py). Touches only
queue/<...>/<id>/item.txt of weapons in the catalogue (a .pre_relabel backup is kept next to it);
the next publish sends the corrected shared schema and the next apply installs it.

  python -I relabel.py [--ids 26035 26042] [--dry-run]
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import labels  # noqa: E402  (also puts kv on the path)
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402
from generate import BASE_SCHEMA, load_schema  # noqa: E402
import pipeline as P  # noqa: E402  (TYPE_NAMES)


def donor_icon(ctx, summ_base):
    """The donor's CURRENT kill icon (item_iconname) from the donor roster built on the installed
    tf2cc base (pipeline.Ctx), or None (stock donors: the weapon class's default icon)."""
    for d in ctx.donors:
        if d["src"] == summ_base["src"] and d["id"] == summ_base["id"]:
            return d["kv"].get("item_iconname")
    return None


def relabel(w, tokens, stock, ctx=None):
    d = os.path.join(ROOT, w["dir"])
    path = os.path.join(d, "item.txt")
    old = open(path, encoding="utf-8").read()
    key, it = kv.parse(old)[0].pairs[0]
    if int(key) != w["defindex"]:
        raise SystemExit("item.txt of %s holds %s" % (w["defindex"], key))
    src = json.load(open(os.path.join(d, "summary.json")))["base"]["src"]
    ic, slot = it.get("item_class"), it.get("item_slot")
    itn = labels.type_token(ic, slot, src, it.get("item_type_name"), tokens, stock) or \
        P.TYPE_NAMES.get(ic, P.re.sub(r"^tf2?c?_weapon_", "", ic).replace("_", " ").title())
    it = kv.KV([(k, itn if k.lower() == "item_type_name" else v) for k, v in it.pairs])
    it = labels.sanitize(it, src, list(w["classes"]))
    if ctx is not None:
        ic = donor_icon(ctx, json.load(open(os.path.join(d, "summary.json")))["base"])
        if ic and it.get("item_iconname") != ic:
            pairs = [(k, v) for k, v in it.pairs if k.lower() != "item_iconname"]
            at = next((i for i, (k, _) in enumerate(pairs) if k.lower() == "item_slot"), len(pairs) - 1) + 1
            pairs.insert(at, ("item_iconname", ic))
            it = kv.KV(pairs)
    new = '"%d"\n{\n%s}\n' % (w["defindex"], kv.dump(it, 1))
    errs = labels.label_check(new, tokens)
    if errs:
        raise SystemExit("still failing after relabel: %s" % errs)
    return path, old, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--iconname", action="store_true", help="also set item_iconname to the donor's current kill icon")
    a = ap.parse_args()
    c = Q.cfg()
    st = Q.load_state(c)
    tokens = labels.tf2c_tokens(c["server_root"])
    stock = labels.stock_types(load_schema(BASE_SCHEMA), tokens)
    ctx = None
    if a.iconname:
        c2 = dict(c)
        c2["_attr_registry"], c2["_used_hues"] = {}, []
        ctx = P.Ctx(c2)
    changed = []
    for k, w in sorted(st["weapons"].items()):
        if w["status"] not in ("approved", "live") or (a.ids and w["defindex"] not in a.ids):
            continue
        path, old, new = relabel(w, tokens, stock, ctx)
        if old == new:
            print("%s ok" % k)
            continue
        print("%s relabelled (%d -> %d bytes)" % (k, len(old), len(new)))
        changed.append(w["defindex"])
        if not a.dry_run:
            bak = path + ".pre_relabel"
            if not os.path.exists(bak):
                shutil.copyfile(path, bak)
            open(path, "w", encoding="utf-8", newline="\n").write(new)
    if changed and not a.dry_run:
        Q.journal(st, "relabel", ids=changed, iconname=bool(a.iconname))
        Q.save_state(st)


if __name__ == "__main__":
    main()
