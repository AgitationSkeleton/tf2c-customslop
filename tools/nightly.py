"""CustomSlop nightly orchestrator (automation mode). All state on disk (state/catalogue.json),
every step idempotent, safe to re-run after a reboot or a killed process; never depends on pm2.

  02:00  python -I nightly.py prepare     (Task Scheduler runs python.exe directly - NOT a .bat, so
                                           KillServers.bat's 02:59 "kill every cmd.exe" can't hit it;
                                           it must finish by 02:45 or it stops itself)
         1. generate daily_count weapons (if tonight's batch doesn't exist yet), auto-approved;
            each weapon passed crash-safety clamps, structural checks and the render gate
         2. publish their assets (+ the union schema: tonight's set plus everything still live,
            so clients that join before 03:00 can still see yesterday's weapons) to the configured
            publish_target in ONE commit through the GitHub Git Data API (no clone), then poll the
            Pages build and HEAD every new URL until 200, plus 10 minutes for the CDN (max-age=600)
         3. mark published=true per weapon; anything unverified simply waits for the next night
         4. engine gate: apply.py --verify-only stages the schema VPK apply will install and boots an
            isolated LAN srcds on it (schemagate.py); the VPK's sha1 is recorded as verified
  03:00  RunServers.bat -> python -I nightly.py apply  (servers are down: KillServers ran 02:59)
         apply.py: lock + journal + rollback; own items only; never blocks the server launch
  03:0x  python -I nightly.py announce    (end of apply; posts only what was applied)

Publishing: prepare runs publish.py --apply (one commit, Pages build + URL verification);
the apply step only applies weapons whose FastDL files were verified.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.append(HERE)
import slopqueue as Q  # noqa: E402

DEADLINE = dt.time(2, 50)          # prepare must be finished before KillCMD (02:58) / the 03:00 apply
APPLY_TIMEOUT = 240                # seconds: the server launch in RunServers.bat waits at most this long


def seconds_left():
    now = dt.datetime.now()
    end = dt.datetime.combine(now.date(), DEADLINE)
    if now.time() > dt.time(12, 0):     # started in the evening (manual run): no deadline pressure
        end += dt.timedelta(days=1)
    return max(0, int((end - now).total_seconds()))


def prepare(a):
    """02:00: generate tonight's weapons (once per date) and publish them to FastDL (one commit,
    Pages build + URL verification). Whatever isn't verified by the deadline waits a night."""
    c = Q.cfg()
    if c["mode"] != "automation" and not a.force:
        sys.exit("review mode: nightly prepare is off (use slopqueue.py for test generations)")
    st = Q.load_state(c)
    today = dt.date.today().isoformat()
    if not any(w.get("created") == today for w in st["weapons"].values()) and not a.publish_only:
        left = seconds_left()
        if left > 20 * 60:
            subprocess.run([sys.executable, "-I", os.path.join(HERE, "slopqueue.py"), "generate",
                            "--count", str(c["daily_count"])], check=False, timeout=min(left - 15 * 60, 40 * 60))
        Q.journal(Q.load_state(c), "prepare_generated", date=today)
    left = seconds_left()
    if left < 5 * 60:
        print("too close to the deadline - publishing waits for the next night")
        return
    try:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "publish.py"), "--apply"], check=False,
                       timeout=max(60, left - 5 * 60))
    except subprocess.TimeoutExpired:
        print("publish timed out; unverified weapons stay unpublished (apply skips them)")
    verify(c)


def verify(c):
    """Engine gate ahead of the 03:00 window: stage exactly what apply will install (same catalogue,
    same live base schema, deterministic vpk.exe build) and boot the isolated gate server on it;
    apply recognises the verified VPK by its sha1 (and runs the gate itself only if time allows)."""
    left = seconds_left()
    if left < 3 * 60:
        print("no time left for the engine gate before the deadline - apply will run it if it can")
        return
    try:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "apply.py"), "--server-root", c["server_root"],
                        "--verify-only"], check=False, timeout=left)
    except subprocess.TimeoutExpired:
        print("engine gate timed out before the deadline")


def publish_plan(st, c):
    """Paths CustomSlop would add to / remove from the FastDL tree (own paths only)."""
    add, rem, ws = [], [], []
    for w in st["weapons"].values():
        if w["status"] in ("approved",) and not w.get("published"):
            ws.append(w["defindex"])
            add += ["tf2classified/%s.bz2" % p for p in w["assets"]]
        if w["status"] == "retired" and w.get("published") and not w.get("unpublished"):
            rem += ["tf2classified/%s.bz2" % p for p in w["assets"]]          # catalogue-listed paths only
    return dict(target=c["publish_target"], weapons=ws, files=add, remove=rem,
                schema="tf2classified/scripts/items/custom_items_game.txt.bz2 (union of live + tonight)")


def run_apply(a):
    """03:00 (inside RunServers.bat, servers down): apply, bounded by APPLY_TIMEOUT so the server
    launch is never blocked; the Discord post runs detached afterwards."""
    c = Q.cfg()
    if c["mode"] != "automation" and not a.force:
        print("review mode: apply skipped")
        return
    env = dict(os.environ, CUSTOMSLOP_LIVE_OK="1")
    try:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "apply.py"), "--server-root", c["server_root"]],
                       timeout=APPLY_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        print("apply timed out - the journal makes the next run roll back or redo it")
    if c.get("discord_enabled"):
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "announce.py")], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "apply", "verify"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--publish-only", action="store_true")
    a = ap.parse_args()
    try:
        {"prepare": prepare, "apply": run_apply, "verify": lambda a_: verify(Q.cfg())}[a.step](a)
    except Exception as e:                 # never fail the caller (RunServers.bat must continue)
        print("nightly %s error: %r" % (a.step, e))
    sys.exit(0)


if __name__ == "__main__":
    main()
