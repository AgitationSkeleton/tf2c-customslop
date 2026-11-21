"""Roll-only simulation of the v2 attribute roller over every donor (no rendering, no state writes):
how often each attribute class appears, jokes per weapon, and that every non-joke stat is on the
reviewed whitelist (attreffect.SPEC) with a value inside its reviewed range."""
import collections
import copy
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import slopqueue as Q  # noqa: E402
import pipeline as PL  # noqa: E402
import attreffect as E  # noqa: E402
import taunts  # noqa: E402

c = copy.deepcopy(Q.cfg())
c["_attr_registry"] = {}          # throwaway: never the catalogue's
c["_used_hues"] = []
ctx = PL.Ctx(c)
donors = ctx.donors if hasattr(ctx, "donors") else ctx.load_donors()
rng = random.Random(20261120)
cls_n, joke_n, per_w, bad, vals = collections.Counter(), collections.Counter(), [], [], collections.defaultdict(list)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 400
for i in range(N):
    attrs = None
    d = donors[rng.randrange(len(donors))]
    classes = d["classes"][:2]
    ic = taunts.fix_item_class(ctx.fs, classes, d["kv"].get("item_class"), d["fam"]) or d["kv"].get("item_class")
    attrs = PL.roll_attributes(ctx, rng, d["fam"], d["slot"], {}, ic, classes)
    per_w.append(len(attrs))
    joke_n[sum(1 for a in attrs if a.get("joke"))] += 1
    for a in attrs:
        if a["cls"] == "custom_projectile_model":
            continue
        cls_n[a["cls"]] += 1
        base = a.get("base_def") or a["name"]
        vals[base].append(a["value"])
        s = E.SPEC.get(base)
        if not s:
            if not a.get("joke") and "customslop" not in base:
                bad.append((base, ic, "not on the whitelist"))
            continue
        if s["v"] and not a.get("joke"):
            lo, hi = min(s["v"]), max(s["v"])
            if not (lo - 1e-9 <= float(a["value"]) <= hi + 1e-9):
                bad.append((base, ic, a["value"], "outside", s["v"]))
        if s["req"] and not a.get("joke"):
            import re
            if not re.search(s["req"], ic or "", re.I):
                bad.append((base, ic, "req fails"))
examples = []
rng2 = random.Random(7)
for _ in range(8):
    d = donors[rng2.randrange(len(donors))]
    classes = d["classes"][:2]
    ic = taunts.fix_item_class(ctx.fs, classes, d["kv"].get("item_class"), d["fam"]) or d["kv"].get("item_class")
    attrs = PL.roll_attributes(ctx, rng2, d["fam"], d["slot"], {}, ic, classes)
    examples.append(dict(item_class=ic, classes=classes, stats=[(a["name"], a["value"]) + (("JOKE",) if a.get("joke") else ())
                                                                for a in attrs]))
observed = {k: [min(v), max(v), len(v)] for k, v in sorted(vals.items())}
res = dict(weapons=N, examples=examples, observed_ranges=observed, mean_attrs=sum(per_w) / N, jokes_per_weapon=dict(joke_n),
           top_classes=cls_n.most_common(25),
           onhit_addhealth_share=round(cls_n["add_onhit_addhealth"] / N, 3),
           onhit_values=sorted(set(vals.get("selfdmg on hit for rapidfire", []) + vals.get("selfdmg on hit for slowfire", []))),
           problems=bad[:40], n_problems=len(bad))
json.dump(res, open(os.path.join(ROOT, "rollsim_result.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
