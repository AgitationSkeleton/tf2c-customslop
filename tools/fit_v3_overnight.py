"""Resumable overnight v3 icon-camera fit (one command, safe to re-run).

  * sets itself to IDLE priority (its 2 worker processes inherit it)
  * skips every donor that already has cache/icon_fit/<key>_v3.json
  * splits the rest over 2 workers (fit_icons.py --v2 --version 3), waits, exits
  * log: tmp/fit_v3_overnight.log (appended)
Writes ONLY cache/icon_fit/*_v3.json and cache/icon_fit/_v3_summary_*.json. Never touches state/,
queue/, config or any server; does not change icon_fit_version (that switch is made after review).

  python -I tools/fit_v3_overnight.py [--dry-run] [--only key,key] [--workers 2]
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, "tmp", "fit_v3_overnight.log")


def idle():
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k32.SetPriorityClass(k32.GetCurrentProcess(), 0x40)          # IDLE_PRIORITY_CLASS


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = "%s %s" % (dt.datetime.now().isoformat(timespec="seconds"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="only list what would be fitted")
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    idle()
    sys.path.insert(0, HERE)
    import iconfit as IF
    import pipeline
    import slopqueue as Q
    c = Q.cfg()
    c["_attr_registry"], c["_used_hues"] = {}, []
    ctx = pipeline.Ctx(c)
    keys = ["%s:%s" % (d["src"], d["id"]) for d in ctx.donors]
    if a.only:
        keys = [k for k in keys if k in a.only.split(",")]
    todo = [k for k in keys if not os.path.exists(IF.cache_path(k, 3))]
    log("v3 fit: %d donors, %d already cached, %d to fit%s" % (len(keys), len(keys) - len(todo), len(todo),
                                                               " (dry run)" if a.dry_run else ""))
    if a.dry_run or not todo:
        for k in todo:
            log("  would fit " + k)
        return
    n = max(1, min(6, a.workers))
    procs = []
    for i in range(n):
        part = todo[i::n]
        if not part:
            continue
        out = open(os.path.join(ROOT, "tmp", "fit_v3_worker%d.log" % i), "a", encoding="utf-8")
        procs.append((i, part, out, subprocess.Popen(
            [sys.executable, "-I", os.path.join(HERE, "fit_icons.py"), "--v2", "--version", "3", "--tag", "w%d" % i,
             "--only", ",".join(part)], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)))
        log("worker %d: %d donors" % (i, len(part)))
    for i, part, out, p in procs:
        rc = p.wait()
        out.close()
        log("worker %d exited rc %s" % (i, rc))
    left = [k for k in todo if not os.path.exists(IF.cache_path(k, 3))]
    log("done: %d fitted, %d still uncached%s" % (len(todo) - len(left), len(left), (": " + ",".join(left)) if left else ""))


if __name__ == "__main__":
    main()
