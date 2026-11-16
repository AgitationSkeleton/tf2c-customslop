"""CustomSlop nightly APPLY step - runs inside the 3 AM window while the TF2C servers are down.

Real timeline on this machine (Task Scheduler, read-only survey 2026-11-16):
  02:59  \\KillServers            KillServers.bat: taskkill srcds_win64.exe ... and EVERY cmd.exe
  03:00  \\Every_Day_3AM_Restart_Servers  RunServers.bat: steamcmd updates, then starts every .lnk in
                                  <your servers folder> (5 s apart); also runs at boot
  03:00  Sundays \\Sunday_3AM_RestartBots  RestartBots.bat: "pm2 restart all" (bots only)
CustomSlop is a plain python process started from RunServers.bat (one line, before the .lnk loop),
so it never depends on pm2 and never sits in a cmd.exe at 02:59.

What it does (only on CustomSlop's own catalogue; HARD_RULES.txt):
  * gates: srcds for the target install must NOT be running; lock file; mode/approved items
  * plan: live' = live + approved(published) - pulled - oldest beyond cap (own items only)
  * build the merged schema = the active non-CustomSlop schema (tf2cc's 00tf2cc_schema.vpk, which
    already includes April Fools) with every CustomSlop-range item removed, then CustomSlop's items
    and attribute definitions appended; verify every non-CustomSlop item/attribute is byte-for-byte
    the same KeyValues as in the base
  * transaction with a journal: back up every target, write new files next to them, os.replace,
    verify; any failure -> roll back from the backups (previous working schema stays); an
    unfinished journal found at start -> roll back first, then plan again (idempotent)
  * targets: custom/00customslop_schema.vpk (sorts before 00tf2cc_schema.vpk, so it is the one
    schema the server reads), the loose scripts/items/custom_items_game.txt (what clients
    download; identical bytes), custom/00customslop/<asset paths> (own paths only),
    addons/sourcemod/configs/customslop/today.cfg (the chat ad text only)
  * no rcon, no restart: RunServers.bat starts the server right after this returns
  * the Discord post is queued only after a successful apply (announce.py sends it)
Always exits 0 within a time budget so a CustomSlop problem can never keep the servers down.

  python -I apply.py --server-root <tf2classified dir> [--dry-run] [--fail-after N]  (test hook)
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths as P  # noqa: E402
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402
import vfs  # noqa: E402

LOCK = os.path.join(Q.STATE_DIR, "apply.lock")
TXN = os.path.join(Q.STATE_DIR, "apply_txn.json")
SCHEMA_VPK = "custom/00customslop_schema.vpk"
ASSET_DIR = "custom/00customslop"
LOOSE = "scripts/items/custom_items_game.txt"
TODAY = "addons/sourcemod/configs/customslop/today.cfg"
DOWNLOADS = "addons/sourcemod/configs/customslop/downloads.txt"   # the plugin adds these to the download table
BASE_VPKS = ["custom/00tf2cc_schema.vpk"]          # non-CustomSlop schema sources, in priority order


# ------------------------------------------------------------------ schema VPK (Valve's vpk.exe)
def build_vpk(path, files, c):
    """files: {relpath: bytes} -> path, built by Valve's vpk.exe (config vpk_exe). A hand-written
    VPK v1 read fine in Python but build 5205 rejected it ("KeyValues Error: LoadFromBuffer:
    missing {"), dropping the whole custom schema, so only vpk.exe output is used - no fallback.
    vpk.exe output is deterministic (same files -> same bytes), so a VPK verified by the engine
    gate at 02:00 is recognised by its sha1 at 03:00."""
    exe = c.get("vpk_exe")
    if not exe or not os.path.isfile(exe):
        raise RuntimeError("vpk.exe not found (config vpk_exe = %r) - refusing; the installed schema stays" % exe)
    work = os.path.join(os.path.dirname(path), "vpkbuild")
    shutil.rmtree(work, ignore_errors=True)
    src = os.path.join(work, "00customslop_schema")
    for rel, b in files.items():
        f = os.path.join(src, rel)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "wb").write(b)
    r = subprocess.run([exe, src], cwd=work, capture_output=True, text=True, timeout=120)
    out = src + ".vpk"
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("vpk.exe failed (rc %s): %s" % (r.returncode, (r.stdout + r.stderr)[-300:]))
    sig, ver = struct.unpack("<II", open(out, "rb").read(8))
    if sig != 0x55AA1234 or ver != 2:
        raise RuntimeError("vpk.exe wrote an unexpected VPK header (%#x v%d)" % (sig, ver))
    os.replace(out, path)
    shutil.rmtree(work, ignore_errors=True)


def gate_ok(st, vp, server_root, c, t0, budget, log):
    """The staged VPK must have passed the engine gate (schemagate.py): looked up by sha1 (prepare
    verifies at 02:00), else run now if the time budget allows two gate boots, else refuse."""
    vsha = sha(open(vp, "rb").read())
    ver = st.setdefault("gate_verified", {})
    if ver.get(vsha, {}).get("ok"):
        log("engine gate: VPK %s already verified (%s, %s items)" % (vsha[:12], ver[vsha]["at"], ver[vsha]["count"]))
        return True
    if "sandbox_server" in server_root.replace("\\", "/") and os.environ.get("CUSTOMSLOP_GATE") != "force":
        log("engine gate skipped (sandbox test run)")
        return True
    left = budget - (time.time() - t0)
    need = 2 * int(c.get("gate_timeout", 60)) + 20
    if left < need:
        log("engine gate: VPK %s not verified and only %ds left (need %ds) - refusing" % (vsha[:12], left, need))
        return False
    import schemagate
    r = schemagate.verify(vp, server_root, c)
    ver[vsha] = dict(ok=r["ok"], at=dt.datetime.now().isoformat(timespec="seconds"), count=r.get("count"),
                     baseline=r.get("baseline"), need=r.get("need"), why=r.get("why"), seconds=r.get("seconds"))
    for k in sorted(ver, key=lambda k: ver[k]["at"])[:-20]:      # keep the last 20 results
        del ver[k]
    log("engine gate: %s in %ss - count %s, need %s %s" % ("PASS" if r["ok"] else "FAIL", r.get("seconds"),
                                                          r.get("count"), r.get("need"), r.get("why") or ""))
    return r["ok"]


# ------------------------------------------------------------------ helpers
def sha(b):
    return hashlib.sha1(b).hexdigest()


def pid_alive(pid):
    """A lock whose owner process is gone (crash, reboot, killed task) is stale."""
    if not pid.isdigit():
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid, "/NH"], capture_output=True, text=True,
                             timeout=20).stdout
    except Exception:
        return True
    return pid in out


def srcds_running(server_root):
    """True if a srcds process serves this game folder (PowerShell CIM query; no rcon).
    Matches on the resolved -game folder, so another server started from the same install with a
    different -game folder (e.g. tf2classified-3\\tf2classified) does not block; anything that
    can't be resolved counts as running."""
    root = os.path.normcase(os.path.abspath(server_root))
    inst = os.path.normcase(os.path.dirname(root))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"name like 'srcds%'\" | "
                              "ForEach-Object { $_.ExecutablePath + [char]9 + $_.CommandLine }"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return True                                   # cannot tell -> be safe, do not apply
    for line in out.splitlines():
        exe, _, cmd = line.strip().partition("\t")
        if not exe:
            continue
        exe_dir = os.path.normcase(os.path.dirname(exe))
        m = re.search(r'-game\s+(?:"([^"]+)"|(\S+))', cmd)
        if not m:
            if exe_dir == inst:
                return True
            continue
        game = m.group(1) or m.group(2)
        if os.path.normcase(os.path.abspath(os.path.join(os.path.dirname(exe), game))) == root:
            return True
    return False


def base_schema(server_root):
    for rel in BASE_VPKS:
        p = os.path.join(server_root, rel)
        if os.path.exists(p):
            b = vfs.VPK(p).read("scripts/items/custom_items_game.txt")
            if b:
                return rel, b
    p = os.path.join(server_root, "custom", "aprilfools2026.vpk")
    return "custom/aprilfools2026.vpk", vfs.VPK(p).read("scripts/items/custom_items_game.txt")


def is_own(k, c):
    return k.isdigit() and c["defindex_first"] - 100 <= int(k) <= c["defindex_last"]


_TOK = __import__("re").compile(r'//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])|([^\s{}"]+)')


def _blocks(text):
    """Byte spans of the depth-2 sections: {'items': (open_brace, close_brace), ...} and the
    spans of every depth-3 key block inside them: {'items': [(key, start, end), ...]}."""
    stack, last, out, kids = [], None, {}, {}
    pend = None
    for m in _TOK.finditer(text):
        if m.group(0).startswith("//"):
            continue
        if m.group(2) == "{":
            stack.append((last, m.start(), pend))
            last, pend = None, None
        elif m.group(2) == "}":
            key, start, kstart = stack.pop()
            if len(stack) == 1 and key in ("items", "attributes"):
                out[key] = (start, m.end())
            if len(stack) == 2 and stack[1][0] in ("items", "attributes"):
                kids.setdefault(stack[1][0], []).append((key, kstart, m.end()))
            last = None
        else:
            tok = m.group(1) if m.group(1) is not None else m.group(3)
            if last is None:
                last, pend = tok, m.start()
            else:
                last, pend = None, None
    return out, kids


MARK_RE = __import__("re").compile(r"\n// ---- CustomSlop \(generated; do not edit\) ----\n.*?// ---- end CustomSlop ----\n",
                                  __import__("re").S)


def cut_own(text, c):
    """Text with every block in CustomSlop's own defindex range cut out (everything else verbatim)."""
    secs, kids = _blocks(text)
    for a, b in sorted([(a, b) for sec in kids for k, a, b in kids[sec] if is_own(k, c)], reverse=True):
        text = text[:a] + text[b:]
    return text


def strip_marked(text):
    """Text with CustomSlop's marked insertion blocks removed = the non-CustomSlop text of a merged file."""
    return MARK_RE.sub("", text)


def strip_sounds(text):
    a = text.find(SND_BEGIN)
    if a >= 0:
        b = text.find(SND_END, a)
        text = text[:a] + text[b + len(SND_END):]
    return text


def merge(base_bytes, live, st, c):
    """Byte-preserving merge: the base text is kept verbatim except that blocks in CustomSlop's own
    defindex range are cut out; CustomSlop's items/attributes are inserted before the closing brace
    of the items / attributes sections. Proof check: removing exactly the inserted spans from the
    result must give back the base text with only own-range blocks removed."""
    text = cut_own(base_bytes.decode("utf-8", errors="replace"), c)
    stripped = text
    secs, _ = _blocks(text)
    frag_items = "".join(open(os.path.join(ROOT, w["dir"], "item.txt"), encoding="utf-8").read() for w in live)
    frag_attrs = Q.attribute_block(st)
    # 5205 rejects the WHOLE custom schema on one bad attribute: re-check every CustomSlop item
    import validate_model as VM
    from generate import BASE_SCHEMA, load_schema
    ig = load_schema(BASE_SCHEMA)
    defs = {a.get("name").lower(): dict(integer=a.get("stored_as_integer") == "1", set_bonus=a.get("is_set_bonus") == "1",
                                        string=a.get("attribute_type") == "string")
            for _, a in ig.get("attributes").blocks() if a.get("name")}
    own = {n.lower(): {} for n in st.get("attr_defs", {})}
    own["customslop ignite self on attack"] = {}
    errs = VM.schema_check(frag_items, defs, own)
    if errs:
        raise RuntimeError("schema gate failed - refusing (5205 would reject the whole schema): %s" % errs[:3])
    import labels
    lerrs = labels.label_check(frag_items, labels.tf2c_tokens(c["server_root"]))
    if lerrs:
        raise RuntimeError("label gate failed - refusing (fix with tools/relabel.py): %s" % lerrs[:3])
    ins = []
    for sec, frag in sorted((("items", frag_items), ("attributes", frag_attrs)), key=lambda x: -secs[x[0]][1]):
        at = secs[sec][1] - 1                                # position of the closing brace
        block = "\n// ---- CustomSlop (generated; do not edit) ----\n" + frag + "// ---- end CustomSlop ----\n"
        text = text[:at] + block + text[at:]
        ins.append((at, len(block)))
    # proof: undo the insertions -> must equal the stripped base exactly
    undo = text
    for at, n in reversed(ins):          # undo in reverse insertion order (later inserts sit lower)
        undo = undo[:at] + undo[at + n:]
    if undo != stripped:
        raise RuntimeError("merge proof failed - refusing")
    root = kv.parse(text)[0].get("items_game")
    base_root = kv.parse(base_bytes.decode("utf-8", errors="replace"))[0].get("items_game")
    for sec in ("items", "attributes"):
        a = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in base_root.get(sec).pairs if not is_own(k, c)}
        b = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in root.get(sec).pairs if not is_own(k, c)}
        if a != b:
            raise RuntimeError("non-CustomSlop %s differ after merge - refusing" % sec)
    return text.encode("utf-8")


SND_BEGIN = "\n// ---- CustomSlop sound scripts (generated; do not edit) ----\n"
SND_END = "// ---- end CustomSlop sound scripts ----\n"


def merge_sounds(base_bytes, live):
    """tf2cc's custom_level_sounds.txt kept byte for byte (its tf2cc.* entries untouched); any old
    CustomSlop block is cut out and the live weapons' customslop.<id>.* scripts appended."""
    text = base_bytes.decode("utf-8", errors="replace")
    a = text.find(SND_BEGIN)
    if a >= 0:
        b = text.find(SND_END, a)
        text = text[:a] + text[b + len(SND_END):]
    base = text
    block = "".join(open(os.path.join(ROOT, w["dir"], "sounds.txt"), encoding="utf-8").read()
                    for w in sorted(live, key=lambda w: w["defindex"])
                    if os.path.exists(os.path.join(ROOT, w["dir"], "sounds.txt")))
    out = base + SND_BEGIN + block + SND_END
    if out[:len(base)] != base or "customslop." in base.replace(SND_BEGIN, ""):
        raise RuntimeError("sound merge proof failed - refusing")
    for name in __import__("re").findall(r'^"([^"]+)"', block, flags=8):
        if not name.startswith("customslop."):
            raise RuntimeError("non-CustomSlop sound script in CustomSlop block: " + name)
    return out.encode("utf-8")


def live_new_for_ad(applied, live):
    """The chat ad lists tonight's newly applied weapons (all of which are live after this apply)."""
    ids = {w["defindex"] for w in live}
    return [w for w in applied if w["defindex"] in ids]


def today_cfg(applied, c):
    ad = "Today's %d new weapons: %s" % (len(applied), ", ".join(
        "%s (%s)" % (w["name"], "/".join(w["classes"])) for w in applied)) if applied else ""
    return ('"CustomSlop"\n{\n\t"date"\t"%s"\n\t"ad"\t"%s"\n}\n'
            % (dt.date.today().isoformat(), ad.replace('"', "'"))).encode("utf-8")


# ------------------------------------------------------------------ transaction
def rollback(server_root, txn, log):
    for step in reversed(txn["steps"]):
        dst = os.path.join(server_root, step["target"])
        if step.get("backup"):
            shutil.copyfile(step["backup"], dst)
        elif step.get("created") and os.path.exists(dst):
            os.remove(dst)
    log("rolled back txn %s (%d steps)" % (txn["id"], len(txn["steps"])))


def apply(server_root, dry=False, fail_after=None, budget=180, verify_only=False):
    """verify_only: plan + stage + engine gate, record the result; never writes the server (02:00)."""
    t0 = time.time()
    c = Q.cfg()
    st = Q.load_state(c)
    logs = []

    def log(m):
        logs.append(m)
        print(m)
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        if pid_alive(open(LOCK).read().strip()) and time.time() - os.path.getmtime(LOCK) < 3600:
            log("another apply holds the lock - skipping")
            return 0
        os.remove(LOCK)
        return apply(server_root, dry, fail_after, budget, verify_only)
    try:
        if os.path.exists(TXN):                                   # half-applied update from a crash
            rollback(server_root, json.load(open(TXN)), log)
            os.remove(TXN)
            Q.journal(st, "apply_recovered_rollback")
        if not verify_only and srcds_running(server_root):
            log("srcds for this install is running - not applying (servers must be down)")
            Q.journal(st, "apply_skipped", why="srcds running")
            Q.save_state(st)
            return 0
        own = {k: w for k, w in st["weapons"].items()}
        for w in own.values():                                    # pulled weapons leave tonight
            if w["status"] == "pull":
                w["status"] = "retired"
        live = [w for w in own.values() if w["status"] == "live" or (w["status"] == "approved" and w.get("published"))]
        live.sort(key=lambda w: (w.get("live_since") or "9999", w["defindex"]))
        retire = live[:max(0, len(live) - c["cap"])]              # oldest beyond the cap (own only)
        live = live[len(retire):]
        applied = [w for w in live if w["status"] == "approved"]
        plugin = os.path.join(server_root, "addons", "sourcemod", "plugins", "customslop.smx")
        if applied and not verify_only and not os.path.exists(plugin) and "sandbox_server" not in server_root:
            # without the plugin the assets never reach the download table: clients would get the
            # schema but not the models - refuse until the plugin is installed
            log("customslop.smx is not installed on the server - not applying new weapons")
            Q.journal(st, "apply_skipped", why="plugin missing")
            Q.save_state(st)
            return 0
        if not applied and not retire and not os.path.exists(os.path.join(server_root, SCHEMA_VPK)):
            log("nothing published to apply yet and CustomSlop is not installed - no changes")
            Q.journal(st, "apply_nothing_to_do")
            Q.save_state(st)
            return 0
        base_rel, base_bytes = base_schema(server_root)          # the base INSTALLED now (never a stored copy)
        base_sha = sha(open(os.path.join(server_root, base_rel), "rb").read())
        prev = next((j for j in reversed(st.get("journal", [])) if j.get("what") == "applied" and j.get("base_vpk_sha1")), None)
        if prev and prev["base_vpk_sha1"] != base_sha:
            log("base %s changed since the last apply (%s -> %s): re-merging on the installed base"
                % (base_rel, prev["base_vpk_sha1"][:12], base_sha[:12]))
        merged = merge(base_bytes, sorted(live, key=lambda w: w["defindex"]), st, c)
        dl = "".join("%s\n" % p_ for w in sorted(live, key=lambda w: w["defindex"]) for p_ in w["assets"])
        plan = {SCHEMA_VPK: None, LOOSE: merged, DOWNLOADS: dl.encode("utf-8")}
        if applied:
            # the chat ad changes only on a night that adds weapons; a night with nothing new keeps
            # the last ad unless it names a weapon that is no longer live
            plan[TODAY] = today_cfg(live_new_for_ad(applied, live), c)
        else:
            tp = os.path.join(server_root, TODAY)
            old = open(tp, encoding="utf-8").read() if os.path.exists(tp) else ""
            if not old or any(w["name"].replace('"', "'") in old for w in retire):
                plan[TODAY] = today_cfg([], c)
        for w in live:
            for p in w["assets"]:
                plan["%s/%s" % (ASSET_DIR, p)] = os.path.join(ROOT, w["dir"], "files", p)
        removals = ["%s/%s" % (ASSET_DIR, p) for w in retire for p in w["assets"]]
        log("plan: base %s, live %d (new %d), retire %d, files %d, removals %d, schema %d bytes"
            % (base_rel, len(live), len(applied), len(retire), len(plan), len(removals), len(merged)))
        if dry:
            return 0
        stage = os.path.join(Q.STATE_DIR, "stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        vp = os.path.join(stage, "00customslop_schema.vpk")
        lsounds = vfs.VPK(os.path.join(server_root, base_rel)).read("scripts/items/custom_level_sounds.txt")
        files = {"scripts/items/custom_items_game.txt": merged}
        files["scripts/items/custom_level_sounds.txt"] = merge_sounds(lsounds or b"", live)
        build_vpk(vp, files, c)
        if vfs.VPK(vp).read("scripts/items/custom_items_game.txt") != merged:
            raise RuntimeError("staged VPK does not read back")
        # engine gate: the staged VPK must be one build 5205 really loads (schemagate.py)
        passed = gate_ok(st, vp, server_root, c, t0, budget, log)
        if verify_only:
            fresh = Q.load_state(c)                                  # record only the gate result
            fresh["gate_verified"] = st.get("gate_verified", {})
            Q.journal(fresh, "gate_verify", ok=passed, vpk_sha1=sha(open(vp, "rb").read()))
            Q.save_state(fresh)
            log("verify-only: engine gate %s; nothing written to the server" % ("PASS" if passed else "FAIL"))
            return 0
        if not passed:
            Q.journal(st, "apply_refused", why="engine gate", vpk_sha1=sha(open(vp, "rb").read()))
            Q.save_state(st)
            log("NOT APPLYING: the staged schema VPK did not pass the engine gate; the installed files stay")
            return 0
        plan[SCHEMA_VPK] = vp
        txn = dict(id=dt.datetime.now().strftime("%Y%m%d-%H%M%S"), steps=[])
        bdir = os.path.join(Q.STATE_DIR, "backups", txn["id"])
        n = 0
        for target, src in list(plan.items()) + [(r, None) for r in removals]:
            if time.time() - t0 > budget:
                raise RuntimeError("time budget exceeded")
            dst = os.path.join(server_root, target)
            step = dict(target=target)
            if os.path.exists(dst):
                os.makedirs(os.path.dirname(os.path.join(bdir, target)), exist_ok=True)
                shutil.copyfile(dst, os.path.join(bdir, target))
                step["backup"] = os.path.join(bdir, target)
            else:
                step["created"] = True
            txn["steps"].append(step)
            json.dump(txn, open(TXN, "w"), indent=1)                 # journal BEFORE touching the target
            if fail_after is not None and n == fail_after:
                raise RuntimeError("injected failure after %d steps" % n)
            if os.environ.get("CUSTOMSLOP_TEST_CRASH_AFTER") == str(n):     # test hook: hard crash
                os._exit(3)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if src is None:                                          # removal of an own retired asset
                if os.path.exists(dst):
                    os.remove(dst)
            else:
                tmp = dst + ".customslop_new"
                if isinstance(src, bytes):
                    open(tmp, "wb").write(src)
                else:
                    shutil.copyfile(src, tmp)
                os.replace(tmp, dst)
            n += 1
        # verify what the server will read
        if open(os.path.join(server_root, LOOSE), "rb").read() != merged or \
                vfs.VPK(os.path.join(server_root, SCHEMA_VPK)).read("scripts/items/custom_items_game.txt") != merged:
            raise RuntimeError("post-apply verification failed")
        os.remove(TXN)
        today = dt.date.today().isoformat()
        for w in applied:
            w["status"], w["live_since"] = "live", today
        for w in retire:
            w["status"], w["retired"] = "retired", today
        if applied:                                  # an apply without new weapons posts nothing
            st.setdefault("announcements", []).append(dict(date=today, txn=txn["id"],
                                                           weapons=[w["defindex"] for w in applied], posted=False))
        Q.journal(st, "applied", txn=txn["id"], new=[w["defindex"] for w in applied],
                  retired=[w["defindex"] for w in retire], schema_sha1=sha(merged), base=base_rel,
                  base_vpk_sha1=base_sha)
        Q.save_state(st)
        log("applied txn %s" % txn["id"])
        return 0
    except Exception as e:
        log("APPLY FAILED: %r" % e)
        if os.path.exists(TXN):
            rollback(server_root, json.load(open(TXN)), log)
            os.remove(TXN)
        Q.journal(st, "apply_failed", error=repr(e)[:300])
        Q.save_state(st)
        return 0
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fail-after", type=int)
    ap.add_argument("--verify-only", action="store_true", help="stage + engine gate only (read-only on the server)")
    a = ap.parse_args()
    live_root = os.path.abspath(Q.cfg().get("server_root") or "").lower()
    if os.path.abspath(a.server_root).lower() == live_root and not os.environ.get("CUSTOMSLOP_LIVE_OK") \
            and not (a.verify_only or a.dry_run):
        sys.exit("refusing to write the live server without CUSTOMSLOP_LIVE_OK=1 (nightly.py apply sets it)")
    sys.exit(apply(a.server_root, a.dry_run, a.fail_after, verify_only=a.verify_only))
