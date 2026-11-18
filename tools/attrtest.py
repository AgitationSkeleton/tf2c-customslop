"""Engine A/B test: do attributes act / persist after a weapon switch and after a respawn?
(user bug: "slow holster/draw time etc persist between lives/weapon changes")

Isolated LAN test server (enginetest/ copy, 127.0.0.1, local RCON with a per-run password, no
client, no Steam), BELOW_NORMAL priority, killed afterwards. Test items = clones of the stock
Soldier shotgun with ONE attribute each. For every case a Soldier bot:
  1. gets the test shotgun (GenerateAndWearItem), switches to it  -> "held"  (speed)
  2. switches melee -> rocket launcher                                -> "switch" (RL deploy delay, speed)
  3. respawns WITHOUT the item (stock loadout)                         -> "respawn" (RL deploy, speed)
Compared with the control case (stock shotgun, no attribute). Writes attrtest_result.json.

  python -I attrtest.py
"""
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
from generate import BASE_SCHEMA, load_schema  # noqa: E402

PORT = 27991
CASES = [  # (defindex, attribute name, class, value, scope per source)
    (29990, None, None, None, "control"),
    (29991, "deploy time increased", "mult_deploy_time", 3.0, "wearer"),
    (29992, "single wep deploy time increased", "mult_single_wep_deploy_time", 3.0, "weapon"),
    (29993, "move speed penalty", "mult_player_movespeed", 0.5, "wearer"),
    (29994, "mult_player_movespeed_active", "mult_player_movespeed_active", 0.5, "active"),
    (29995, "single wep holster time increased", "mult_switch_from_wep_deploy_time", 3.0, "wearer"),
]

NUT = r'''
function AT_Bot() { return Entities.FindByClassname(null, "player"); }
function AT_Slot(p, s) {
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (w && w.GetSlot() == s) return w;
    }
    return null;
}
function AT_Log(s) { printl("ATTRTEST " + s); }
function AT_Give(name) { local p = AT_Bot(); p.GenerateAndWearItem(name); local w = AT_Slot(p, 1); if (w) p.Weapon_Switch(w); }
function AT_Melee() { local p = AT_Bot(); local w = AT_Slot(p, 2); if (w) p.Weapon_Switch(w); }
function AT_Primary(tag) {
    local p = AT_Bot(); local w = AT_Slot(p, 0);
    if (!w) { AT_Log(tag + " noprimary"); return; }
    p.Weapon_Switch(w);
    local d = NetProps.GetPropFloat(w, "LocalActiveWeaponData.m_flNextPrimaryAttack") - Time();
    AT_Log(tag + " deploy " + d);
}
function AT_Speed(tag) { local p = AT_Bot(); AT_Log(tag + " speed " + NetProps.GetPropFloat(p, "m_flMaxspeed") + " sec " + (AT_Slot(p, 1) ? NetProps.GetPropInt(AT_Slot(p, 1), "m_AttributeManager.m_Item.m_iItemDefinitionIndex") : -1)); }
function AT_Respawn() { local p = AT_Bot(); p.ForceRespawn(); }
'''


def build_schema():
    base_rel, base = A.base_schema(ET.LIVE)
    st = load_schema(BASE_SCHEMA)
    stock = dict(st.get("items").blocks())["10"]                     # stock Soldier shotgun
    pf = {k.lower(): b for k, b in st.get("prefabs").blocks()} if st.get("prefabs") else {}
    import labels
    frag = ""
    for di, an, cls, val, _ in CASES:
        it = kv.KV()
        it.add("name", "customslop_attrtest_%d" % di)
        for key in ("item_class", "item_slot", "item_quality", "model_player", "model_world", "attach_to_hands",
                    "anim_slot", "item_type_name", "item_name"):
            v = labels._eff(stock, key, pf)
            if v is not None:
                it.add(key, v)
        ubc = kv.KV()
        ubc.add("Soldier", "1")
        it.add("used_by_classes", ubc)
        if an:
            at, b = kv.KV(), kv.KV()
            b.add("attribute_class", cls)
            b.add("value", str(val))
            at.add(an, b)
            it.add("attributes", at)
        frag += '"%d"\n{\n%s}\n' % (di, kv.dump(it, 1))
    text = base.decode("utf-8", errors="replace")
    secs, _ = A._blocks(text)
    at_ = secs["items"][1] - 1
    return (text[:at_] + frag + text[at_:]).encode("utf-8"), base_rel


def main():
    schema, base_rel = build_schema()
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write(schema)
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_attrtest.nut"), "w").write(NUT)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_attrtest.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_waitingforplayers_cancel 1",
                                     "tf_bot_reevaluate_class_in_spawnroom 0", 'rcon_password "%s"' % pw,
                                     "script_execute customslop_attrtest", ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "4", "+servercfgfile", "customslop_attrtest.cfg", "+map", "ctf_2fort"]
    p = subprocess.Popen(cmd, cwd=ET.ET, creationflags=subprocess.CREATE_NEW_CONSOLE | 0x4000)
    res = dict(cases=[], raw=[])
    try:
        t0 = time.time()
        while not (os.path.exists(log) and "SV_ActivateServer" in open(log, encoding="utf-8", errors="replace").read()):
            if p.poll() is not None or time.time() - t0 > 150:
                raise RuntimeError("server did not start")
            time.sleep(2)
        time.sleep(4)
        r = ET.Rcon(PORT, pw)
        resp = []
        _cmd = r.cmd
        r.cmd = lambda c_: (resp.append(_cmd(c_)), resp[-1])[1]
        r.cmd("sv_cheats 1")
        r.cmd("script_execute customslop_attrtest")
        r.cmd("tf_bot_add 1 soldier red")
        time.sleep(8)
        for di, an, cls, val, sc in CASES:
            nm = "customslop_attrtest_%d" % di
            r.cmd("script AT_Respawn()")
            time.sleep(2)
            r.cmd('script AT_Give("%s")' % nm)
            time.sleep(1.5)
            r.cmd('script AT_Speed("%d held")' % di)
            r.cmd("script AT_Melee()")
            time.sleep(1.5)
            r.cmd('script AT_Primary("%d switch")' % di)
            time.sleep(1.5)
            r.cmd('script AT_Speed("%d switch")' % di)
            r.cmd("script AT_Respawn()")
            time.sleep(2.5)
            r.cmd("script AT_Melee()")
            time.sleep(1.5)
            r.cmd('script AT_Primary("%d respawn")' % di)
            time.sleep(1.5)
            r.cmd('script AT_Speed("%d respawn")' % di)
        time.sleep(1)
        try:
            r.cmd("quit")
        except Exception:
            pass
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        open(cfgp, "w").write("// rcon password removed after the run\n")
    txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    try:
        txt += chr(10) + chr(10).join(resp)
    except NameError:
        pass
    lines = [l.split("ATTRTEST ", 1)[1] for l in txt.splitlines() if "ATTRTEST " in l]
    res["errors"] = [l for l in txt.splitlines() if "ERROR" in l or "does not exist" in l or "Unknown" in l][:20]
    res["raw"] = lines
    vals = {}
    for l in lines:
        m = re.match(r"(\d+) (\w+) (deploy|speed) ([-0-9.e]+)(?: sec (-?\d+))?", l)
        if m:
            vals.setdefault(int(m.group(1)), {})["%s_%s" % (m.group(2), m.group(3))] = float(m.group(4))
            if m.group(5) is not None:
                vals[int(m.group(1))]["%s_secondary" % m.group(2)] = int(m.group(5))
    ctl = vals.get(29990, {})
    for di, an, cls, val, sc in CASES:
        v = vals.get(di, {})
        row = dict(defindex=di, attribute=an, cls=cls, value=val, scope_per_source=sc, **v)
        if di != 29990:
            for k in ("switch_deploy", "switch_speed", "respawn_deploy", "respawn_speed", "held_speed"):
                if k in v and k in ctl:
                    row[k + "_vs_control"] = round(v[k] - ctl[k], 3)
        res["cases"].append(row)
    json.dump(res, open(os.path.join(ROOT, "attrtest_result.json"), "w"), indent=1)
    print(json.dumps(res["cases"], indent=1))


if __name__ == "__main__":
    main()
