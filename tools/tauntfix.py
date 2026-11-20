"""Make CustomSlop's catalogued live weapons taunt for the classes they're given to, in place
(same defindex, same classes, same model): item_class -> a behaviour-equivalent class that every
wielding class has a taunt rule for (taunts.fix_item_class: generic shotgun/pistol translated per
class, the class's own stock melee, or "saxxy" for multi-class melee). Weapons without such a
class are reported and left unchanged (changing their weapon type or classes would change the
weapon or break loadouts). Backups item.txt.pre_taunt; journal "tauntfix".

  python -I tauntfix.py [--dry-run]
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import labels  # noqa: E402  (puts kv on the path)
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402
import taunts  # noqa: E402
import vfs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    st = Q.load_state(Q.cfg())
    fs = vfs.VFS()
    changed, report = [], []
    for k, w in sorted(st["weapons"].items()):
        if w["status"] not in ("live", "approved"):
            continue
        d = os.path.join(ROOT, w["dir"])
        path = os.path.join(d, "item.txt")
        key, it = kv.parse(open(path, encoding="utf-8").read())[0].pairs[0]
        ic = it.get("item_class")
        cls = [c for c, _ in it.get("used_by_classes").pairs]
        fam = json.load(open(os.path.join(d, "summary.json"))).get("family")
        before = {c: taunts.ok(fs, c, ic) for c in cls}
        fix = taunts.fix_item_class(fs, cls, ic, fam)
        row = dict(defindex=int(k), classes=cls, item_class=ic, taunt_before=before)
        if fix and fix != ic:
            row.update(new_item_class=fix, taunt_after={c: taunts.ok(fs, c, fix) for c in cls})
            if not a.dry_run:
                if not os.path.exists(path + ".pre_taunt"):
                    shutil.copyfile(path, path + ".pre_taunt")
                it = kv.KV([(kk, fix if kk == "item_class" else v) for kk, v in it.pairs])
                open(path, "w", encoding="utf-8", newline="\n").write('"%s"\n{\n%s}\n' % (key, kv.dump(it, 1)))
            changed.append(int(k))
        elif not all(before.values()):
            row["note"] = "no behaviour-equivalent item_class lets every class taunt - unchanged"
        report.append(row)
        print(json.dumps(row))
    if changed and not a.dry_run:
        Q.journal(st, "tauntfix", ids=changed)
        Q.save_state(st)
    json.dump(report, open(os.path.join(ROOT, "tauntfix_result%s.json" % ("_dryrun" if a.dry_run else "")), "w"), indent=1)


if __name__ == "__main__":
    main()
