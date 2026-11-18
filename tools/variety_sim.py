"""Simulate the nightly donor choice with the variety rules (slopqueue.type_history +
pipeline.pick_donor, the code the generator uses): N nights x daily_count picks starting from the
REAL catalogue's history (read-only). Checks: no weapon type in two consecutive nights' batches,
distinct types within a night; reports the type sequence. Writes variety_sim_result.json.

  python -I variety_sim.py [--nights 60] [--seed 5]
"""
import argparse
import collections
import copy
import datetime as dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pipeline  # noqa: E402
import slopqueue as Q  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nights", type=int, default=60)
    ap.add_argument("--seed", type=int, default=5)
    a = ap.parse_args()
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    st = copy.deepcopy(Q.load_state(c))
    rng = random.Random(a.seed)
    day0 = dt.date.today()
    seq, issues = [], []
    n = c.get("daily_count", 3)
    for night in range(a.nights):
        date = (day0 + dt.timedelta(days=night)).isoformat()
        prev, recent = Q.type_history(st, date)
        taken_t, taken_s, batch = set(), set(), []
        for k in range(n):
            d = pipeline.pick_donor(rng, ctx.donors, dict(avoid_types=sorted(prev | taken_t), recent_types=recent,
                                                         taken_slots=sorted(taken_s)))
            t = pipeline.weapon_type(d["kv"].get("item_class"))
            if t in prev:
                issues.append("%s: %s repeats last night's type" % (date, t))
            if t in taken_t:
                issues.append("%s: %s twice in one batch" % (date, t))
            taken_t.add(t)
            taken_s.add(d["slot"])
            batch.append(dict(type=t, slot=d["slot"], donor="%s:%s" % (d["src"], d["id"])))
            st["weapons"]["sim%d_%d" % (night, k)] = dict(created=date, status="live", base=dict(item_class=t))
        seq.append(dict(date=date, avoided=sorted(prev), batch=batch))
    types = collections.Counter(b["type"] for s in seq for b in s["batch"])
    slots_per_night = collections.Counter(len({b["slot"] for b in s["batch"]}) for s in seq)
    out = dict(nights=a.nights, issues=issues, ok=not issues, distinct_types=len(types),
               type_counts=types.most_common(), distinct_slots_per_night=dict(slots_per_night),
               first_night=seq[0], sequence=[[b["type"].replace("tf_weapon_", "").replace("tf2c_weapon_", "c:")
                                              for b in s["batch"]] for s in seq])
    json.dump(out, open(os.path.join(ROOT, "variety_sim_result.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("nights", "ok", "issues", "distinct_types", "distinct_slots_per_night")}))
    print("tonight avoids:", seq[0]["avoided"], "-> picks", [b["type"] for b in seq[0]["batch"]])
    for i, s in enumerate(out["sequence"][:15]):
        print(i, s)


if __name__ == "__main__":
    main()
