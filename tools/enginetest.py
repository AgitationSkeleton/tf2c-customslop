"""Real engine load test for CustomSlop weapons on an ISOLATED, bots-only TF2C dedicated server.

The server runs from enginetest/ (a copy of the test server's binaries inside this research
folder); its only writable game dir is enginetest/tf2classified. Game content is mounted
read-only from the TF2C #2 install (see enginetest/tf2classified/gameinfo.txt). LAN only
(+sv_lan 1, -insecure, 127.0.0.1, port 27999), no Steam login, no game client.

For the given weapons: the merged schema (live tf2cc/April Fools base + the candidates), their
sound scripts and assets are mounted first. At map load a VScript precaches every view/world
model and spawns a prop_dynamic of each. Then, over local RCON (per-run random password, never
stored), a bot of each candidate's class is added, given the item (GenerateAndWearItem),
switched to it, and the weapon's class/model is printed; then the server quits.
Pass = clean exit, every model precached (index > 0), every bot got its item, no Host_Error /
Bad model / error.mdl / "not found" lines for CustomSlop paths in console.log.

  python -I enginetest.py <defindex> [<defindex> ...]
"""
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import apply as A  # noqa: E402
import slopqueue as Q  # noqa: E402
import vfs  # noqa: E402
import cspaths as P  # noqa: E402

ET = P.opt("enginetest_dir") or os.path.join(ROOT, "enginetest")
GAME = os.path.join(ET, "tf2classified")
CUSTOM = os.path.join(GAME, "custom", "customslop_test")
LIVE = P.server_root()
CLASS_CMD = {"Scout": "scout", "Soldier": "soldier", "Pyro": "pyro", "Demoman": "demoman", "Heavy": "heavyweapons",
             "Engineer": "engineer", "Medic": "medic", "Sniper": "sniper", "Spy": "spy", "Civilian": "civilian"}
CLASS_ID = {"Scout": 1, "Sniper": 2, "Soldier": 3, "Demoman": 4, "Medic": 5, "Heavy": 6, "Pyro": 7, "Spy": 8,
            "Engineer": 9, "Civilian": 10}
NL = chr(10)
NUL = bytes(1)

NUT = r'''
// CustomSlop engine-load test (generated)
::CS_W <- %(weapons)s;
::CS_MODELS <- %(models)s;
function CS_Log(s) { printl("CUSTOMSLOP_TEST " + s); }
function CS_Step1()
{
    foreach (i, m in ::CS_MODELS)
    {
        local idx = PrecacheModel(m);
        CS_Log("precache " + m + " index " + idx);
        local p = SpawnEntityFromTable("prop_dynamic", { model = m, origin = Vector(0, 0, -10000 + i * 64) });
        CS_Log("prop " + m + " -> " + (p ? p.GetModelName() : "FAILED"));
    }
    CS_Log("STEP1_DONE");
}
function CS_Bots()
{
    // the isolated test server has no human players: every player entity is one of our bots
    local out = [];
    local p = null;
    while ((p = Entities.FindByClassname(p, "player")) != null) out.append(p);
    return out;
}
function CS_Prepare()
{
    local bots = CS_Bots();
    CS_Log("bots " + bots.len());
    foreach (k, w in ::CS_W)
    {
        if (k >= bots.len()) { CS_Log("item " + w.id + " no bot"); continue; }
        local p = bots[k];
        p.SetPlayerClass(w.classid);
        NetProps.SetPropInt(p, "m_Shared.m_iDesiredPlayerClass", w.classid);
        p.ForceRegenerateAndRespawn();
        CS_Log("bot " + k + " -> class " + p.GetPlayerClass() + " alive " + p.IsAlive());
    }
}
function CS_Step2()
{
    local bots = CS_Bots();
    foreach (k, w in ::CS_W)
    {
        if (k >= bots.len()) continue;
        local p = bots[k];
        p.GenerateAndWearItem(w.item);
        local got = null;
        for (local s = 0; s < 48; s++)
        {
            local wep = NetProps.GetPropEntityArray(p, "m_hMyWeapons", s);
            if (wep && NetProps.GetPropInt(wep, "m_AttributeManager.m_Item.m_iItemDefinitionIndex") == w.id) got = wep;
        }
        if (got) { p.Weapon_Switch(got); CS_Log("item " + w.id + " ok class " + got.GetClassname() + " model " + got.GetModelName() + " bot class " + p.GetPlayerClass()); }
        else CS_Log("item " + w.id + " MISSING on bot");
    }
    CS_Log("DONE");
}
CS_Step1();
'''


class Rcon:
    """Minimal Source RCON client, for the local test server only (127.0.0.1)."""

    def __init__(self, port, password):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=15)
        self.id = 0
        self.send(3, password)
        self.read()
        self.read()

    def send(self, typ, body):
        self.id += 1
        b = body.encode() + NUL + NUL
        self.s.sendall(struct.pack("<iii", len(b) + 8, self.id, typ) + b)

    def read(self):
        n = struct.unpack("<i", self.s.recv(4))[0]
        data = b""
        while len(data) < n:
            data += self.s.recv(n - len(data))
        return data[8:-2].decode(errors="replace")

    def cmd(self, c):
        self.send(2, c)
        return self.read()


def build(ids):
    st = Q.load_state(Q.cfg())
    ws = [st["weapons"][str(i)] for i in ids]
    shutil.rmtree(CUSTOM, ignore_errors=True)
    os.makedirs(os.path.join(CUSTOM, "scripts", "items"))
    for w in ws:
        shutil.copytree(os.path.join(ROOT, w["dir"], "files"), CUSTOM, dirs_exist_ok=True)
    base_rel, base = A.base_schema(LIVE)
    merged = A.merge(base, ws, st, Q.cfg())
    open(os.path.join(CUSTOM, "scripts", "items", "custom_items_game.txt"), "wb").write(merged)
    lsounds = vfs.VPK(os.path.join(LIVE, base_rel)).read("scripts/items/custom_level_sounds.txt") or b""
    open(os.path.join(CUSTOM, "scripts", "items", "custom_level_sounds.txt"), "wb").write(A.merge_sounds(lsounds, ws))
    models, weapons = [], []
    for w in ws:
        models += [p for p in w["assets"] if p.endswith(".mdl")]
        cls = next(iter(w["classes"]))
        weapons.append('{ id = %d, item = "customslop_%d", cls = "%s", classid = %d }'
                       % (w["defindex"], w["defindex"], CLASS_CMD[cls], CLASS_ID[cls]))
    os.makedirs(os.path.join(GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(GAME, "scripts", "vscripts", "customslop_test.nut"), "w").write(
        NUT % dict(weapons="[" + ", ".join(weapons) + "]", models="[" + ", ".join('"%s"' % m for m in models) + "]"))
    return ws, models


def run(ids, timeout=240):
    ws, models = build(ids)
    pw = secrets.token_hex(12)                       # per-run, local only, never stored
    cfgp = os.path.join(GAME, "cfg", "customslop_test.cfg")
    os.makedirs(os.path.dirname(cfgp), exist_ok=True)
    open(cfgp, "w").write(NL.join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0", "tf_bot_join_after_player 0",
                                   "mp_timelimit 0", "mp_waitingforplayers_cancel 1", 'rcon_password "%s"' % pw,
                                   "script_execute customslop_test", ""]))
    log = os.path.join(GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET, "srcds_win64.exe"), "-game", GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", "27999", "+clientport", "27998",
           "+tv_enable", "0", "+maxplayers", "8", "+tf_allow_server_hibernation", "0",
           "+servercfgfile", "customslop_test.cfg", "+map", "ctf_2fort"]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=ET, creationflags=subprocess.CREATE_NEW_CONSOLE)   # -console needs a real console
    rc, steps = None, []

    def logtxt():
        return open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    try:
        while "STEP1_DONE" not in logtxt():
            if p.poll() is not None or time.time() - t0 > 150:
                raise RuntimeError("server did not finish loading (rc %s)" % p.poll())
            time.sleep(2)
        time.sleep(3)
        r = Rcon(27999, pw)
        for w in ws:
            steps.append(r.cmd("tf_bot_add 1 %s red" % CLASS_CMD[next(iter(w["classes"]))]))
        time.sleep(10)
        steps.append(r.cmd("script CS_Prepare()"))
        time.sleep(4)
        steps.append(r.cmd("script CS_Step2()"))
        t1 = time.time()
        time.sleep(3)
        try:
            r.cmd("quit")
        except Exception:
            pass
        rc = p.wait(timeout=60)
    except Exception as e:
        steps.append("ERROR %r" % e)
        p.kill()
        rc = "killed"
    finally:
        open(cfgp, "w").write("// rcon password removed after the run" + NL)
    txt = logtxt()
    lines = [l for l in (txt + NL + NL.join(steps)).splitlines() if "CUSTOMSLOP_TEST" in l]
    errs = [l for l in txt.splitlines() if re.search(r"(Host_Error|Bad model|error[.]mdl|not found|Failed to load|"
                                                    r"too many|overflow|crash)", l, re.I) and "customslop" in l.lower()]
    errs += [l for l in txt.splitlines() if "Item schema load failed" in l or "Context '" in l]
    res = dict(returncode=rc, seconds=round(time.time() - t0), models=len(models), log_lines=lines, errors=errs,
               rcon_steps=[s_[:160] for s_ in steps])
    pre_ok = sum(1 for l in lines if " precache " in l) == len(models) and \
        all(re.search(r"index [1-9][0-9]*", l) for l in lines if " precache " in l)
    items_ok = all(any(("item %d ok" % w["defindex"]) in l for l in lines) for w in ws)
    # the server must actually use CustomSlop's model for the weapon (some bases override it)
    model_ok = {w["defindex"]: any(("item %d ok" % w["defindex"]) in l and "customslop/cs%d/" % w["defindex"] in l
                                   for l in lines) for w in ws}
    res["model_used_per_item"] = model_ok
    items_ok = items_ok and all(model_ok.values())
    res.update(precache_ok=pre_ok, items_ok=items_ok, done=any("CUSTOMSLOP_TEST DONE" in l for l in lines),
               passed=bool(pre_ok and items_ok and not errs and any("CUSTOMSLOP_TEST DONE" in l for l in lines)))
    json.dump(res, open(os.path.join(ROOT, "enginetest_result.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(run([int(x) for x in sys.argv[1:]]), indent=1))
