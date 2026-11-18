"""Attribute validation table (source-based, TF2C 5205 / 2024 game source):
attribute | attribute_class | verdict | item classes it works on.
verdicts:  works        read on this weapon / the active weapon for >= 1 CustomSlop item class
           persists     read on the PLAYER (every equipped item, across weapon switches and lives)
           no-effect    weapon-scoped but read only by item classes CustomSlop never rolls it onto
           unverified   no read site in the game source (e.g. hype_on_damage)
           vscript      CustomSlop's own VScript effect (needs the VScript installed on the server)
Also lists the LIVE weapons' attributes with their verdict on that weapon's item class.
Writes attribute_validation.json + attribute_validation.tsv in the research root.

  python -I attrtable.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import attrscope as A  # noqa: E402
import generate as G  # noqa: E402
import slopqueue as Q  # noqa: E402


def verdict(p, cl, ln, ics):
    if p.get("vscript"):
        return "vscript", []
    info = cl.get(p["cls"])
    if not info:
        return "unverified", []
    if info["verdict"] != "safe":
        return "persists" if info["verdict"] == "persists" else "other-scope", []
    ok = [ic for ic in ics if A.works_on(info, ic, ln)]
    return ("works" if ok else "no-effect"), ok


def main():
    cl, ln = A.load()
    ics = sorted({c for f in G.FAMILY.values() for c in f})
    pool = [p for p in json.load(open(os.path.join(ROOT, "analysis", "attribute_pool_5205.json"))) if p["disposition"] != "excluded"]
    rows = []
    for p in pool:
        v, ok = verdict(p, cl, ln, ics)
        rows.append(dict(name=p["name"], cls=p["cls"], verdict=v, works_on=ok if len(ok) < len(ics) else ["(all)"]))
    by = {}
    for r in rows:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    live = []
    st = Q.load_state(Q.cfg())
    import kv
    names = {p["name"].lower(): p for p in pool}
    for k, w in sorted(st["weapons"].items()):
        if w["status"] not in ("live", "approved"):
            continue
        it = kv.parse(open(os.path.join(ROOT, w["dir"], "item.txt"), encoding="utf-8").read())[0].pairs[0][1]
        ic = it.get("item_class")
        for n, b in (it.get("attributes").blocks() if it.get("attributes") else []):
            p = names.get(n.lower()) or dict(name=n, cls=b.get("attribute_class"))
            v, ok = verdict(p, cl, ln, [ic])
            live.append(dict(weapon=int(k), item_class=ic, attribute=n, cls=b.get("attribute_class"),
                             verdict=v if v != "no-effect" else "no-effect on " + ic))
    out = dict(summary=by, attributes=rows, live_weapons=live)
    json.dump(out, open(os.path.join(ROOT, "attribute_validation.json"), "w"), indent=1)
    with open(os.path.join(ROOT, "attribute_validation.tsv"), "w", encoding="utf-8") as f:
        f.write("attribute\tattribute_class\tverdict\titem classes it works on\n")
        for r in sorted(rows, key=lambda r: (r["verdict"], r["cls"])):
            f.write("%s\t%s\t%s\t%s\n" % (r["name"], r["cls"], r["verdict"], ",".join(r["works_on"])))
    print(json.dumps(by))
    for x in live:
        print(x)


if __name__ == "__main__":
    main()
