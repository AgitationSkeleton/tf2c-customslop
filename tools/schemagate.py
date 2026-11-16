"""Engine gate for CustomSlop's schema VPK: boot an ISOLATED dedicated server with the staged
custom/00customslop_schema.vpk and require that build 5205 actually loads it.

Why: on 2026-11-16 a VPK v1 written by apply.py read fine in Python (vfs.VPK) but the engine
printed "KeyValues Error: LoadFromBuffer: missing { in file scripts/items/custom_items_game.txt"
and dropped the WHOLE custom schema (tf2cc Merc, April Fools and CustomSlop items fell back to
stock). Only the engine can say whether it reads the file, so the gate asks the engine.

The gate server:
  * runs the enginetest/ copy of the live install's binaries (re-synced from the live install
    whenever a file's size/mtime differs, so it is always the engine build the live server runs);
  * its own game dir enginetest/gate/tf2classified/: gameinfo.txt generated from the live gameinfo.txt,
    custom/ holding ONLY the staged VPK (mounted by the same custom/* wildcard as live), then every
    non-CustomSlop entry of the target server's custom/ mounted read-only by absolute path in the
    same alphabetical order, then the live vpks/ and TF2/HL2 content read-only;
  * Metamod + SourceMod core + tf2attributes_tf2c.smx only (copied from the server's addons/),
    whose "[tf2attributes_tf2c.smx] Item schema: A attributes, N items with static attributes."
    line reports what the engine really loaded;
  * LAN only: +sv_lan 1, 127.0.0.1, -insecure, -nomaster, -nohltv, no rcon, no Steam login,
    no game client; killed (whole process tree) when the check is done, on any error and on
    timeout; a leftover gate server from a crashed run is killed before the next one starts.

Pass = the server reached the map, no "KeyValues Error" / "Item schema load failed" line for
scripts/items/*, and N >= N_baseline + the number of CustomSlop items in the staged schema, where
N_baseline is the count with no CustomSlop VPK (tf2cc's VPK alone; cached by input hashes).

  python -I schemagate.py <staged.vpk> [--server-root <tf2classified>]   (prints the result JSON)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cspaths as CP  # noqa: E402
import slopqueue as Q  # noqa: E402
import vfs  # noqa: E402

ET = CP.opt("enginetest_dir") or os.path.join(ROOT, "enginetest")   # copy of the live install's srcds binaries
GATE = os.path.join(ET, "gate", "tf2classified")      # the gate server's own game dir (tf2attributes_tf2c
#                                                       only runs in a game folder named tf2classified)
OWN_PREFIX = "00customslop"                           # CustomSlop's entries in custom/
SCHEMA = "scripts/items/custom_items_game.txt"
COUNT_RE = re.compile(r"Item schema: (\d+) attributes, (\d+) items with static attributes")
BAD_RE = re.compile(r"KeyValues Error|Item schema load failed|failed to load item schema", re.I)
NL = chr(10)


def sha_file(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _sync(src, dst):
    """Copy files whose size/mtime differ (src is only read)."""
    n = 0
    for dp, _, fs in os.walk(src):
        for f in fs:
            s = os.path.join(dp, f)
            d = os.path.join(dst, os.path.relpath(s, src))
            if not os.path.exists(d) or os.path.getsize(s) != os.path.getsize(d) or \
                    int(os.path.getmtime(s)) != int(os.path.getmtime(d)):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                n += 1
    return n


def sync_binaries(live_root):
    """The gate must run the engine build the live server runs."""
    inst = os.path.dirname(os.path.abspath(live_root))
    n = _sync(os.path.join(inst, "bin"), os.path.join(ET, "bin"))
    for f in os.listdir(ET):
        s = os.path.join(inst, f)
        if f.lower().endswith((".exe", ".dll")) and os.path.isfile(s) and \
                (os.path.getsize(s) != os.path.getsize(os.path.join(ET, f)) or
                 int(os.path.getmtime(s)) != int(os.path.getmtime(os.path.join(ET, f)))):
            shutil.copy2(s, os.path.join(ET, f))
            n += 1
    n += _sync(os.path.join(live_root, "bin"), os.path.join(GATE, "bin"))
    return n


def setup_addons(live_root):
    """Metamod + SourceMod core + tf2attributes_tf2c.smx only (copied once; refreshed when the
    plugin or SourceMod changes)."""
    src = os.path.join(live_root, "addons")
    dst = os.path.join(GATE, "addons")
    plugin = os.path.join(src, "sourcemod", "plugins", "tf2attributes_tf2c.smx")
    if not os.path.exists(plugin):
        raise RuntimeError("the gate needs tf2attributes_tf2c.smx on the server (addons/sourcemod/plugins)")
    stamp = sha_file(plugin) + sha_file(os.path.join(src, "sourcemod", "bin", "x64", "sourcemod.2.tf2.dll")
                                        if os.path.exists(os.path.join(src, "sourcemod", "bin", "x64", "sourcemod.2.tf2.dll"))
                                        else plugin)
    marker = os.path.join(dst, "customslop_gate.stamp")
    if os.path.exists(marker) and open(marker).read() == stamp:
        return
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "metamod"))
    for f in ("metamod.vdf", "metamod_x64.vdf"):
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    shutil.copytree(os.path.join(src, "metamod", "bin"), os.path.join(dst, "metamod", "bin"))
    shutil.copy2(os.path.join(src, "metamod", "sourcemod.vdf"), os.path.join(dst, "metamod", "sourcemod.vdf"))
    sm, dsm = os.path.join(src, "sourcemod"), os.path.join(dst, "sourcemod")
    for d in ("bin", "gamedata", "translations"):
        shutil.copytree(os.path.join(sm, d), os.path.join(dsm, d))
    shutil.copytree(os.path.join(sm, "extensions"), os.path.join(dsm, "extensions"),
                    ignore=shutil.ignore_patterns("updater*", "webternet*", "dbi.mysql*", "dbi.pgsql*", "*.autoload"))
    os.makedirs(os.path.join(dsm, "configs"))
    for f in ("core.cfg", "databases.cfg", "languages.cfg", "admin_levels.cfg", "admin_groups.cfg",
              "admin_overrides.cfg"):
        shutil.copy2(os.path.join(sm, "configs", f), os.path.join(dsm, "configs", f))
    for d in ("plugins", "data", "logs"):
        os.makedirs(os.path.join(dsm, d))
    shutil.copy2(plugin, os.path.join(dsm, "plugins", "tf2attributes_tf2c.smx"))
    open(marker, "w").write(stamp)


def write_gameinfo(live_root, target_root):
    """gameinfo.txt from the live one: custom/* = the gate's own custom/ (staged VPK only), then the
    target server's non-CustomSlop custom entries read-only, in the same order; every other
    |gameinfo_path| entry points at the live install read-only, except the write paths and bin."""
    txt = open(os.path.join(live_root, "gameinfo.txt"), encoding="utf-8", errors="replace").read()
    custom = os.path.join(target_root, "custom")
    others = sorted(e for e in os.listdir(custom) if not e.lower().startswith(OWN_PREFIX))
    if any(e.lower() < OWN_PREFIX for e in others):
        raise RuntimeError("a custom/ entry sorts before CustomSlop's: the gate cannot keep the live order")
    out = []
    for line in txt.splitlines():
        m = re.match(r'^(\s*)(\S+)(\s+)\|gameinfo_path\|(\S*)\s*$', line)
        if m and not line.strip().startswith("//"):
            ind, kind, sp, rel = m.groups()
            if rel == "custom/*":
                out.append(line)
                for e in others:
                    out.append('%s%s%s"%s"' % (ind, kind, sp, os.path.join(custom, e)))
                continue
            if rel not in (".", "bin", "download"):
                line = '%s%s%s"%s"' % (ind, kind, sp, os.path.normpath(os.path.join(live_root, rel)))
        out.append(line)
    # the stock game dir of the live install, read-only, for maps / scripts not in a VPK
    for i in range(len(out) - 1, -1, -1):
        if "gamebin" in out[i] and "|gameinfo_path|bin" in out[i]:
            out.insert(i + 1, '\t\t\tgame\t\t\t\t"%s"' % live_root)
            break
    open(os.path.join(GATE, "gameinfo.txt"), "w", encoding="utf-8").write(NL.join(out) + NL)
    return others


def kill_leftovers():
    """Kill a gate server left by a crashed run (only processes whose -game is the gate dir)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"name like 'srcds%'\" | "
                              "ForEach-Object { [string]$_.ProcessId + [char]9 + $_.CommandLine }"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    for line in out.splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit() and GATE.lower() in cmd.lower():
            subprocess.run(["taskkill", "/PID", pid.strip(), "/T", "/F"], capture_output=True)


def boot(vpk, timeout, port):
    """One gate boot. vpk=None -> baseline (no CustomSlop VPK). Returns (count, bad_lines, info)."""
    cdir = os.path.join(GATE, "custom")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(cdir)
    if vpk:
        shutil.copyfile(vpk, os.path.join(cdir, "00customslop_schema.vpk"))
    os.makedirs(os.path.join(GATE, "cfg"), exist_ok=True)
    open(os.path.join(GATE, "cfg", "customslop_gate.cfg"), "w").write(NL.join(
        ["sv_lan 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0", "mp_timelimit 0", 'rcon_password ""', ""]))
    log = os.path.join(GATE, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET, "srcds_win64.exe"), "-game", GATE, "-console", "-insecure", "-nomaster", "-nohltv",
           "-nocrashdialog", "-condebug", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(port),
           "+clientport", str(port - 1), "+tv_enable", "0", "+maxplayers", "2",
           "+servercfgfile", "customslop_gate.cfg", "+map", "ctf_2fort"]
    kill_leftovers()
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=ET, creationflags=subprocess.CREATE_NEW_CONSOLE)   # -console needs a console

    def txt():
        return open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    try:
        while True:
            t = txt()
            if "SV_ActivateServer" in t and COUNT_RE.search(t) and time.time() - t0 > 3:
                time.sleep(2)
                break
            if p.poll() is not None:
                break
            if time.time() - t0 > timeout:
                break
            time.sleep(1)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            try:
                p.wait(timeout=20)
            except Exception:
                p.kill()
        kill_leftovers()
    t = txt()
    counts = [int(m.group(2)) for m in COUNT_RE.finditer(t)]
    bad = [l.strip() for l in t.splitlines() if BAD_RE.search(l) and ("scripts/items" in l.replace("\\", "/") or
                                                                     "schema" in l.lower())]
    info = dict(seconds=round(time.time() - t0, 1), reached_map="SV_ActivateServer" in t, counts=counts,
                exit=p.returncode)
    return (counts[-1] if counts else None), bad, info


def baseline(c, live_root, target_root, port, timeout):
    """Count with tf2cc's VPK alone (no CustomSlop VPK), cached by every input that changes it."""
    custom = os.path.join(target_root, "custom")
    parts = [sha_file(os.path.join(live_root, "bin", "x64", "server.dll"))]
    for e in sorted(os.listdir(custom)):
        p = os.path.join(custom, e)
        if e.lower().startswith(OWN_PREFIX):
            continue
        if os.path.isfile(p):
            parts.append(e + sha_file(p))
        else:
            for rel in (SCHEMA, "scripts/items/custom_level_sounds.txt"):
                q = os.path.join(p, rel)
                if os.path.exists(q):
                    parts.append(e + rel + sha_file(q))
    key = hashlib.sha1("|".join(parts).encode()).hexdigest()
    cache = os.path.join(Q.STATE_DIR, "gate_baseline.json")
    if os.path.exists(cache):
        d = json.load(open(cache))
        if d.get("key") == key and d.get("count"):
            return d
    n, bad, info = boot(None, timeout, port)
    d = dict(key=key, count=n, bad=bad, info=info, at=time.strftime("%Y-%m-%d %H:%M:%S"))
    if n:
        json.dump(d, open(cache, "w"), indent=1)
    return d


def verify(vpk, target_root=None, c=None):
    """Engine-check one staged schema VPK. Returns a result dict with ok=True/False."""
    c = c or Q.cfg()
    live_root = c["server_root"]
    target_root = target_root or live_root
    port, timeout = int(c.get("gate_port", 27993)), int(c.get("gate_timeout", 120))
    t0 = time.time()
    res = dict(vpk_sha1=sha_file(vpk), target=target_root)
    try:
        os.makedirs(GATE, exist_ok=True)
        res["synced_files"] = sync_binaries(live_root)
        setup_addons(live_root)
        res["mounted_after_staged"] = write_gameinfo(live_root, target_root)
        txt = vfs.VPK(vpk).read(SCHEMA)
        if not txt:
            raise RuntimeError("staged VPK has no %s" % SCHEMA)
        own = len(set(re.findall(rb'^"(2[6-9]\d{3})"\s*$', txt, flags=re.M)))
        base = baseline(c, live_root, target_root, port, timeout)
        n, bad, info = boot(vpk, timeout, port)
        res.update(own_items=own, baseline=base.get("count"), baseline_bad=base.get("bad"), count=n, bad=bad,
                   boot=info, need=(base.get("count") or 0) + own)
        why = []
        if not base.get("count"):
            why.append("baseline boot gave no item-schema count (%s)" % base.get("info"))
        if not info["reached_map"]:
            why.append("gate server did not reach the map")
        if bad:
            why.append("engine errors: %s" % bad[:3])
        if n is None:
            why.append("no item-schema count")
        elif base.get("count") and n < base["count"] + own:
            why.append("engine loaded %d items with static attributes, need >= %d (baseline %d + %d CustomSlop)"
                       % (n, base["count"] + own, base["count"], own))
        res["ok"] = not why
        res["why"] = why
    except Exception as e:
        res["ok"] = False
        res["why"] = ["gate error: %r" % e]
        kill_leftovers()
    res["seconds"] = round(time.time() - t0, 1)
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("vpk")
    ap.add_argument("--server-root")
    a = ap.parse_args()
    print(json.dumps(verify(a.vpk, a.server_root), indent=1))
