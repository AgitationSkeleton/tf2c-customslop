"""Engine test: can each class taunt with a CustomSlop-style item? (user: "get the weapons it adds to
be able to taunt via the classes they're given to")

5205 picks a weapon taunt with response rules on TLK_PLAYER_TAUNT keyed on the player class and
"playerweapon" = the ACTIVE weapon entity's classname (item_class after TranslateWeaponEntForClass:
"tf_weapon_shotgun" -> _soldier/_hwg/_pyro/_primary, "saxxy" -> the class's stock melee); there is
no default rule, so an item whose entity class has no rule for that class cannot taunt.

Isolated LAN server (enginetest/ copy, local RCON with a per-run password, BELOW_NORMAL, killed
afterwards). Test items (all classes): saxxy melee, generic shotgun, a rocket launcher, plus any
--items "<item_class>:<slot>" pairs. Per class: give each item, switch to it, log the entity
classname, call Taunt and check TF_COND_TAUNTING. Writes taunttest_result.json.

  python -I taunttest.py [--items tf_weapon_bat:melee,...]
"""
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import apply as A  # noqa: E402
import enginetest as ET  # noqa: E402
import kv  # noqa: E402

PORT = 27989
CLASSES = [("Scout", 1), ("Sniper", 2), ("Soldier", 3), ("Demoman", 4), ("Medic", 5), ("Heavy", 6), ("Pyro", 7),
           ("Spy", 8), ("Engineer", 9), ("Civilian", 10)]
SLOT_N = {"primary": 0, "secondary": 1, "melee": 2}

NUT = r'''
function TT_Bot() { return Entities.FindByClassname(null, "player"); }
function TT_Log(s) { printl("TAUNTTEST " + s); }
function TT_Class(cid) {
    local p = TT_Bot(); p.SetPlayerClass(cid);
    NetProps.SetPropInt(p, "m_Shared.m_iDesiredPlayerClass", cid);
    p.ForceRegenerateAndRespawn();
}
function TT_Give(name, di) {
    local p = TT_Bot(); p.GenerateAndWearItem(name);
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (w && NetProps.GetPropInt(w, "m_AttributeManager.m_Item.m_iItemDefinitionIndex") == di) {
            p.Weapon_Switch(w); TT_Log(di + " class " + p.GetPlayerClass() + " entity " + w.GetClassname()); return;
        }
    }
    TT_Log(di + " class " + p.GetPlayerClass() + " entity MISSING");
}
function TT_Taunt() {
    local p = TT_Bot();
    try { p.Taunt(0, 0); } catch (e) { try { p.HandleTauntCommand(0); } catch (e2) { TT_Log("no taunt function"); } }
}
function TT_Check(di) { local p = TT_Bot(); local a = p.GetActiveWeapon();
    TT_Log(di + " class " + p.GetPlayerClass() + " taunting " + (p.InCond(7) ? 1 : 0) + " active " + (a ? a.GetClassname() : "none")); }
function TT_Pre(di) { local p = TT_Bot(); TT_Log(di + " class " + p.GetPlayerClass() + " before " + (p.InCond(7) ? 1 : 0)); }
'''


def build_schema(items):
    base_rel, base = A.base_schema(ET.LIVE)
    frag = ""
    for di, ic, slot in items:
        it = kv.KV()
        for k, v in (("name", "customslop_taunttest_%d" % di), ("item_class", ic), ("item_slot", slot),
                     ("item_quality", "unique"), ("item_type_name", "#TF_Weapon_Shovel"), ("item_name", "taunttest %d" % di)):
            it.add(k, v)
        ubc = kv.KV()
        for c, _ in CLASSES:
            ubc.add(c, "1")
        it.add("used_by_classes", ubc)
        frag += '"%d"\n{\n%s}\n' % (di, kv.dump(it, 1))
    text = base.decode("utf-8", errors="replace")
    secs, _ = A._blocks(text)
    at_ = secs["items"][1] - 1
    return (text[:at_] + frag + text[at_:]).encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="")
    a = ap.parse_args()
    items = [(29980, "saxxy", "melee"), (29981, "tf_weapon_shotgun", "secondary"), (29982, "tf_weapon_rocketlauncher", "primary")]
    for k, x in enumerate(t for t in a.items.split(",") if t):
        ic, slot = x.split(":")
        items.append((29983 + k, ic, slot))
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write(build_schema(items))
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_taunttest.nut"), "w").write(NUT)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_taunttest.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_waitingforplayers_cancel 1",
                                     'rcon_password "%s"' % pw, ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "4", "+servercfgfile", "customslop_taunttest.cfg", "+map", "ctf_2fort"]
    p = subprocess.Popen(cmd, cwd=ET.ET, creationflags=subprocess.CREATE_NEW_CONSOLE | 0x40,   # IDLE priority
                         startupinfo=ET.quiet_console())                          # minimised, no focus
    resp = []
    try:
        t0 = time.time()
        while not (os.path.exists(log) and "SV_ActivateServer" in open(log, encoding="utf-8", errors="replace").read()):
            if p.poll() is not None or time.time() - t0 > 150:
                raise RuntimeError("server did not start")
            time.sleep(2)
        time.sleep(4)
        r = ET.Rcon(PORT, pw)
        _cmd = r.cmd
        r.cmd = lambda c_: (resp.append(_cmd(c_)), resp[-1])[1]
        r.cmd("sv_cheats 1")
        r.cmd("script_execute customslop_taunttest")
        r.cmd("tf_bot_add 1 soldier red")
        time.sleep(8)
        r.cmd("nb_blind 1")
        for cname, cid in CLASSES:
            r.cmd("script TT_Class(%d)" % cid)
            time.sleep(4.0)
            for di, ic, slot in items:
                r.cmd('script TT_Give("customslop_taunttest_%d", %d)' % (di, di))
                time.sleep(1.5)
                r.cmd("script TT_Pre(%d)" % di)
                r.cmd("script TT_Taunt()")
                time.sleep(0.5)
                r.cmd("script TT_Check(%d)" % di)
                time.sleep(7.0)                          # let the taunt finish before the next item
        try:
            r.cmd("quit")
        except Exception:
            pass
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=ET.NO_WINDOW)
        open(cfgp, "w").write("// rcon password removed after the run\n")
    txt = (open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else "") + "\n" + "\n".join(resp)
    lines = [l.split("TAUNTTEST ", 1)[1] for l in txt.splitlines() if "TAUNTTEST " in l]
    res = {}
    cname = {cid: n for n, cid in CLASSES}
    for l in lines:
        m = re.match(r"(\d+) class (\d+) entity (\S+)", l)
        if m:
            res.setdefault(cname.get(int(m.group(2)), m.group(2)), {}).setdefault(int(m.group(1)), {})["entity"] = m.group(3)
        m0 = re.match(r"(\d+) class (\d+) before (\d)", l)
        if m0:
            res.setdefault(cname.get(int(m0.group(2)), m0.group(2)), {}).setdefault(int(m0.group(1)), {})["before"] = m0.group(3) == "1"
        m = re.match(r"(\d+) class (\d+) taunting (\d)(?: active (\S+))?", l)
        if m:
            e = res.setdefault(cname.get(int(m.group(2)), m.group(2)), {}).setdefault(int(m.group(1)), {})
            e["taunt"] = m.group(3) == "1"
            e["active"] = m.group(4)
    out = dict(items={di: dict(item_class=ic, slot=slot) for di, ic, slot in items}, results=res,
               notes=[l for l in lines if "no taunt function" in l][:3])
    json.dump(out, open(os.path.join(ROOT, "taunttest_result.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
