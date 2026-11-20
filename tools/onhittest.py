"""Engine test: what does a CustomSlop health-on-hit attribute do in 5205? (user bug: "negative
health on hit attributes don't actually work and instead just grant 3 health on hit")

Isolated LAN test server (attrtest/enginetest copy, 127.0.0.1, local RCON with a per-run password,
no client, no Steam), IDLE priority, killed afterwards. Test items = clones of the stock Soldier
shotgun with ONE attribute each (attrtest.build_schema). Per case a RED Soldier bot gets the item,
is set to 100 health, and a BLU Heavy bot takes 10 damage from it through TakeDamageEx (attacker =
the Soldier, weapon = the test item) - the engine's own damage path, so ApplyOnHitAttributes runs.
The attacker's health before/after (same script call, nothing else can interfere) is logged.
Writes onhittest_result.json.

  python -I onhittest.py
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
import attrtest as AT  # noqa: E402
import enginetest as ET  # noqa: E402

PORT = 27987
CASES = [  # (defindex, attribute name, class, value, note)
    (29980, None, None, None, "control"),
    (29981, "heal on hit for rapidfire", "add_onhit_addhealth", 20, "positive"),
    (29982, "selfdmg on hit for rapidfire", "add_onhit_addhealth", -18, "negative (as live 26057/26058/26064/26065)"),
    (29983, "heal on hit for slowfire", "add_onhit_addhealth", 27, "positive"),
    (29984, "selfdmg on hit for slowfire", "add_onhit_addhealth", -15, "negative (as live 26074)"),
    (29985, "heal on hit for rapidfire", "add_onhit_addhealth", -12, "negative value on the positive definition"),
    (29986, "crit mod disabled", "mult_crit_chance", 0, "logs crit chance via the weapon (sanity)"),
]

NUT = r'''
function OH_Bot(team) {
    local p = null;
    while (p = Entities.FindByClassname(p, "player")) if (p.GetTeam() == team) return p;
    return null;
}
function OH_Slot(p, s) {
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (w && w.GetSlot() == s) return w;
    }
    return null;
}
function OH_Log(s) { printl("ONHIT " + s); }
function OH_Give(name) { local p = OH_Bot(2); p.GenerateAndWearItem(name); local w = OH_Slot(p, 1); if (w) p.Weapon_Switch(w); }
function OH_Hit(tag) {
    local a = OH_Bot(2), v = OH_Bot(3);
    if (!a || !v) { OH_Log(tag + " nobots"); return; }
    local w = OH_Slot(a, 1);
    if (!w) { OH_Log(tag + " noweapon"); return; }
    local di = NetProps.GetPropInt(w, "m_AttributeManager.m_Item.m_iItemDefinitionIndex");
    a.SetHealth(100); v.SetHealth(300);
    local h0 = a.GetHealth(), vh0 = v.GetHealth();
    v.TakeDamageEx(w, a, w, Vector(0, 0, 0), v.GetOrigin(), 10.0, 2);
    OH_Log(tag + " def " + di + " attacker " + h0 + " " + a.GetHealth() + " victim " + vh0 + " " + v.GetHealth()
           + " alive " + (NetProps.GetPropInt(a, "m_lifeState") == 0 ? 1 : 0));
}
function OH_Respawn() { local p = OH_Bot(2); p.ForceRespawn(); local v = OH_Bot(3); if (v) v.ForceRespawn(); }
'''


def main():
    AT.CASES = [(di, an, cls, val, note) for di, an, cls, val, note in CASES]
    schema, _ = AT.build_schema()
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write(schema)
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_onhittest.nut"), "w").write(NUT)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_onhittest.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_waitingforplayers_cancel 1",
                                     "mp_teams_unbalance_limit 0", "mp_autoteambalance 0",
                                     "tf_bot_reevaluate_class_in_spawnroom 0", 'rcon_password "%s"' % pw,
                                     "script_execute customslop_onhittest", ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "4", "+servercfgfile", "customslop_onhittest.cfg", "+map", "ctf_2fort"]
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
        r.cmd("script_execute customslop_onhittest")
        r.cmd("tf_bot_add 1 soldier red")
        r.cmd("tf_bot_add 1 heavyweapons blue")
        time.sleep(10)
        for rep in range(2):
            for di, an, cls, val, note in CASES:
                r.cmd("script OH_Respawn()")
                time.sleep(2)
                r.cmd('script OH_Give("customslop_attrtest_%d")' % di)
                time.sleep(1.5)
                r.cmd('script OH_Hit("%d r%d")' % (di, rep))
                time.sleep(0.5)
        try:
            r.cmd("quit")
        except Exception:
            pass
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=ET.NO_WINDOW)
        open(cfgp, "w").write("// rcon password removed after the run\n")
    txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    txt += chr(10) + chr(10).join(x for x in resp if isinstance(x, str))
    lines = [l.split("ONHIT ", 1)[1] for l in txt.splitlines() if "ONHIT " in l]
    res = dict(raw=lines, errors=[l for l in txt.splitlines() if "ERROR" in l or "does not exist" in l][:20], cases=[])
    got = {}
    for l in lines:
        m = re.match(r"(\d+) r(\d) def (-?\d+) attacker (\d+) (\d+) victim (\d+) (\d+)", l)
        if m:
            got.setdefault(int(m.group(1)), []).append(dict(defindex_held=int(m.group(3)),
                                                           attacker_delta=int(m.group(5)) - int(m.group(4)),
                                                           victim_delta=int(m.group(7)) - int(m.group(6))))
    for di, an, cls, val, note in CASES:
        res["cases"].append(dict(defindex=di, attribute=an, value=val, note=note, runs=got.get(di, [])))
    json.dump(res, open(os.path.join(ROOT, "onhittest_result.json"), "w"), indent=1)
    print(json.dumps(res["cases"], indent=1))


if __name__ == "__main__":
    main()
