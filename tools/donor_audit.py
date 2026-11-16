"""Audit every donor once (identity copy, no deformation): engine-safety checks on the view and
world model, and the class-arms bonemerge for each class the donor could be given to.
Writes cache/donor_audit.json; pipeline.Ctx drops donors that fail engine checks and only assigns
classes whose arms bonemerge onto the donor's view model.

  python -I donor_audit.py
"""
import collections
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mutate as MU  # noqa: E402
import pipeline  # noqa: E402
import slopqueue  # noqa: E402
import srcmodel as S  # noqa: E402
import validate_model as VM  # noqa: E402
import vmrender as VMR  # noqa: E402
from generate import CLASSES  # noqa: E402

OUT = os.path.join(ROOT, "cache", "donor_audit.json")


def arms_path(c):
    return "models/weapons/c_models/c_%s_arms.mdl" % {"Demoman": "demo"}.get(c, c.lower())


def main():
    c = slopqueue.cfg()
    c["_attr_registry"] = {}
    ctx = pipeline.Ctx(c, audit=False)
    arms = {}
    for cl in CLASSES:
        p = pipeline.extract_model(ctx, arms_path(cl), os.path.join(ROOT, "tmp", "arms"))
        arms[cl] = S.load(p) if os.path.exists(p) else None
    res = {}
    for d in ctx.donors:
        key = "%s:%s" % (d["src"], d["id"])
        tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, "tmp"))
        saved, ctx.fs = ctx.fs, d["fs"]
        try:
            r = dict(src=d["src"], id=d["id"], mp=d["mp"], mw=d["mw"], engine={}, arms={}, ok=True, reasons=[])
            for kind, rel in (("v", d["mp"]), ("w", d["mw"])):
                if not rel:
                    continue
                src = pipeline.extract_model(ctx, rel, os.path.join(tmp, "src"))
                try:
                    MU.mutate(src, tmp, "models/customslop/audit/%s.mdl" % kind, "models/customslop/audit", dict(stretch=1.0))
                    e = VM.engine_checks(os.path.join(tmp, "models/customslop/audit/%s.mdl" % kind), None, ctx.fs, src)
                    e.pop("materials", None)          # no recolour in the audit
                    bad = [k for k, (ok, _) in e.items() if not ok]
                except Exception as ex:
                    bad = ["exception: %r" % ex]
                r["engine"][kind] = bad
                if bad:
                    r["ok"] = False
                    r["reasons"].append("%s: %s" % (kind, bad))
                if kind == "v":
                    vm = S.load(src)
                    att = int(d["kv"].get("attach_to_hands") or 2)
                    for cl in CLASSES:
                        if att != 2 or arms[cl] is None:
                            r["arms"][cl] = True
                        else:
                            r["arms"][cl] = VMR.arms_bonemerge_report(vm, arms[cl])["ok"]
            if not any(r["arms"].values()):
                r["ok"] = False
                r["reasons"].append("no class arms bonemerge onto the view model")
            res[key] = r
        finally:
            ctx.fs = saved
            shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    by = collections.Counter((r["src"], r["ok"]) for r in res.values())
    print(json.dumps({"%s %s" % k: v for k, v in sorted(by.items())}, indent=1))
    for k, r in res.items():
        if not r["ok"]:
            print(k, r["mp"].split("/")[-1], r["reasons"][:2])


if __name__ == "__main__":
    main()
