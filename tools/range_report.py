"""Old (a184e8e) vs new value ranges per whitelisted definition -> analysis/value_ranges_5205.tsv"""
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import attreffect as NEW  # noqa: E402
import pipeline as PL  # noqa: E402

old_src = subprocess.run(["git", "show", "a184e8e:tools/attreffect.py"], cwd=ROOT, capture_output=True, text=True).stdout
spec = importlib.util.spec_from_loader("attreffect_old", loader=None)
OLD = importlib.util.module_from_spec(spec)
exec(old_src, OLD.__dict__)
pool = {p["name"]: p for p in json.load(open(os.path.join(ROOT, "analysis", "attribute_pool_5205.json")))}
obs = json.load(open(os.path.join(ROOT, "rollsim_result.json"))).get("observed_ranges", {})
rows = ["definition\tattribute_class\told_min\told_max\tnew_min\tnew_max\trolled_min\trolled_max\tn_rolled"]
for name in sorted(NEW.SPEC):
    p = pool.get(name)
    if not p:
        continue
    o, n = OLD.SPEC.get(name), NEW.SPEC[name]
    if n["v"]:
        nlo, nhi = min(n["v"]), max(n["v"])
    elif p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage") and p["direction"] != "flag":
        lo, hi = PL.safety_range(p)
        sem = PL.semantic_side(p)
        up = (sem == "up") if sem else ((p["direction"] == "pos") == (p["fmt"] == "value_is_percentage"))
        nlo, nhi = (1.05, hi) if up else (lo, 0.95)
    else:
        nlo = nhi = 1
    if o and o["v"]:
        olo, ohi = min(o["v"]), max(o["v"])
    elif nlo == nhi:
        olo, ohi = nlo, nhi
    else:   # old generic mild roll (12% "big swing": up to 4.0 / down to 0.1)
        olo, ohi = ((1.1, 1.5) if nlo >= 1 else (0.6, 0.9))
    ob = obs.get(name) or ["", "", 0]
    rows.append("\t".join(str(x) for x in (name, p["cls"], olo, ohi, nlo, nhi, ob[0], ob[1], ob[2])))
open(os.path.join(ROOT, "analysis", "value_ranges_5205.tsv"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
