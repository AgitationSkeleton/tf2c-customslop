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


# ------------------------------------------------------------------ VPK writer (v1, single file)
def write_vpk(path, files):
    """files: {relpath: bytes}. VPK v1 directory with the data embedded (archive 0x7fff)."""
    tree = bytearray()
    data = bytearray()
    by_ext = {}
    for rel, b in sorted(files.items()):
        d, fn = os.path.split(rel.replace("\\", "/"))
        name, ext = fn.rsplit(".", 1)
        by_ext.setdefault(ext, {}).setdefault(d or " ", []).append((name, b))
    for ext, dirs in by_ext.items():
        tree += ext.encode() + b"\0"
        for d, entries in dirs.items():
            tree += d.encode() + b"\0"
            for name, b in entries:
                tree += name.encode() + b"\0"
                crc = __import__("zlib").crc32(b) & 0xFFFFFFFF
                tree += struct.pack("<IHHIIH", crc, 0, 0x7FFF, len(data), len(b), 0xFFFF)
                data += b
            tree += b"\0"
        tree += b"\0"
    tree += b"\0"
    out = struct.pack("<III", 0x55AA1234, 1, len(tree)) + bytes(tree) + bytes(data)
    open(path, "wb").write(out)


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
    """True if a srcds process runs from this install (PowerShell CIM query; no rcon)."""
    inst = os.path.dirname(os.path.abspath(server_root)).lower()
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"name like 'srcds%'\" | "
                              "ForEach-Object { $_.ExecutablePath }"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return True                                   # cannot tell -> be safe, do not apply
    return any(l.strip().lower().startswith(inst) for l in out.splitlines() if l.strip())


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


def merge(base_bytes, live, st, c):
    """Byte-preserving merge: the base text is kept verbatim except that blocks in CustomSlop's own
    defindex range are cut out; CustomSlop's items/attributes are inserted before the closing brace
    of the items / attributes sections. Proof check: removing exactly the inserted spans from the
    result must give back the base text with only own-range blocks removed."""
    text = base_bytes.decode("utf-8", errors="replace")
    secs, kids = _blocks(text)
    cut = sorted([(a, b) for sec in kids for k, a, b in kids[sec] if is_own(k, c)], reverse=True)
    for a, b in cut:
        text = text[:a] + text[b:]
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


def apply(server_root, dry=False, fail_after=None, budget=180):
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
        return apply(server_root, dry, fail_after, budget)
    try:
        if os.path.exists(TXN):                                   # half-applied update from a crash
            rollback(server_root, json.load(open(TXN)), log)
            os.remove(TXN)
            Q.journal(st, "apply_recovered_rollback")
        if srcds_running(server_root):
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
        if applied and not os.path.exists(plugin) and "sandbox_server" not in server_root:
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
        base_rel, base_bytes = base_schema(server_root)
        merged = merge(base_bytes, sorted(live, key=lambda w: w["defindex"]), st, c)
        dl = "".join("%s\n" % p_ for w in sorted(live, key=lambda w: w["defindex"]) for p_ in w["assets"])
        plan = {SCHEMA_VPK: None, LOOSE: merged, TODAY: today_cfg(live_new_for_ad(applied, live), c),
                DOWNLOADS: dl.encode("utf-8")}
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
        write_vpk(vp, files)
        if vfs.VPK(vp).read("scripts/items/custom_items_game.txt") != merged:
            raise RuntimeError("staged VPK does not read back")
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
        st.setdefault("announcements", []).append(dict(date=today, txn=txn["id"], weapons=[w["defindex"] for w in applied],
                                                       posted=False))
        Q.journal(st, "applied", txn=txn["id"], new=[w["defindex"] for w in applied],
                  retired=[w["defindex"] for w in retire], schema_sha1=sha(merged))
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
    a = ap.parse_args()
    live_root = os.path.abspath(Q.DEFAULT_CFG["server_root"]).lower()
    if os.path.abspath(a.server_root).lower() == live_root and not os.environ.get("CUSTOMSLOP_LIVE_OK"):
        sys.exit("refusing to touch the live server from the research prototype")
    sys.exit(apply(a.server_root, a.dry_run, a.fail_after))
