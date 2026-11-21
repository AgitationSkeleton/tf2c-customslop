"""Engine probe: which weapon entity (and script bucket = the client's slot key) does 5205 create for
an item_class, per player class? Isolated LAN server (enginetest copy, 127.0.0.1, per-run RCON
password, no client, no Steam, IDLE, minimised console). For every family item class CustomSlop
uses and every class, a bot gets a stock-model item of that item_class; logged: entity classname
and GetSlot(). Writes analysis/weapon_buckets_5205.json:
  {item_class: {class: [entity_classname, bucket]}}

  python -I bucketprobe.py
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
from generate import BASE_SCHEMA, FAMILY, load_schema  # noqa: E402

PORT = 27981
BOT = {"Scout": "scout", "Soldier": "soldier", "Pyro": "pyro", "Demoman": "demoman", "Heavy": "heavyweapons",
       "Engineer": "engineer", "Medic": "medic", "Sniper": "sniper", "Spy": "spy"}
CIDX = {"Scout": 1, "Sniper": 2, "Soldier": 3, "Demoman": 4, "Medic": 5, "Heavy": 6, "Pyro": 7, "Spy": 8, "Engineer": 9}

NUT = r'''
function BP_Bot(c) {
    local p = null;
    while (p = Entities.FindByClassname(p, "player")) if (p.GetPlayerClass() == c) return p;
    return null;
}
function BP_Run(tag, c, name, di) {
    local p = BP_Bot(c);
    if (!p) { printl("BUCKET " + tag + " nobot"); return; }
    p.GenerateAndWearItem(name);
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (w && NetProps.GetPropInt(w, "m_AttributeManager.m_Item.m_iItemDefinitionIndex") == di) {
            printl("BUCKET " + tag + " " + w.GetClassname() + " " + w.GetSlot());
            return;
        }
    }
    printl("BUCKET " + tag + " none -1");
}
'''


def main():
    st = load_schema(BASE_SCHEMA)
    stock = dict(st.get("items").blocks())["10"]
    import labels
    pf = {k.lower(): b for k, b in st.get("prefabs").blocks()} if st.get("prefabs") else {}
    ics = sorted({ic for f, s in FAMILY.items() for ic in s} | {"saxxy", "tf_weapon_shotgun_primary"})
    frag, cases, di = "", [], 29800
    for ic in ics:
        it = kv.KV()
        it.add("name", "customslop_bucket_%d" % di)
        for key in ("item_quality", "model_player", "model_world", "attach_to_hands", "item_type_name", "item_name"):
            v = labels._eff(stock, key, pf)
            if v is not None:
                it.add(key, v)
        it.add("item_class", ic)
        it.add("item_slot", "primary")
        ubc = kv.KV()
        for c in BOT:
            ubc.add(c, "1")
        it.add("used_by_classes", ubc)
        frag += '"%d"\n{\n%s}\n' % (di, kv.dump(it, 1))
        for c in BOT:
            cases.append((ic, c, di))
        di += 1
    base_rel, text = A.base_schema(ET.LIVE)
    text = text.decode("utf-8", errors="replace")
    secs, _ = A._blocks(text)
    at_ = secs["items"][1] - 1
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write((text[:at_] + frag + text[at_:]).encode("utf-8"))
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_bucketprobe.nut"), "w").write(NUT)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_bucketprobe.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_waitingforplayers_cancel 1",
                                     "mp_teams_unbalance_limit 0", "mp_autoteambalance 0", 'rcon_password "%s"' % pw, ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "12", "+servercfgfile", "customslop_bucketprobe.cfg", "+map", "ctf_2fort"]
    p = subprocess.Popen(cmd, cwd=ET.ET, creationflags=subprocess.CREATE_NEW_CONSOLE | 0x40, startupinfo=ET.quiet_console())
    resp = []
    try:
        t0 = time.time()
        while not (os.path.exists(log) and "SV_ActivateServer" in open(log, encoding="utf-8", errors="replace").read()):
            if p.poll() is not None or time.time() - t0 > 150:
                raise RuntimeError("server did not start")
            time.sleep(2)
        time.sleep(4)
        r = ET.Rcon(PORT, pw)
        r.cmd("sv_cheats 1")
        resp.append(r.cmd("script_execute customslop_bucketprobe") or "")
        for c in BOT.values():
            r.cmd("tf_bot_add 1 %s red" % c)
        time.sleep(10)
        for ic, c, d in cases:
            resp.append(r.cmd('script BP_Run("%s|%s", %d, "customslop_bucket_%d", %d)' % (ic, c, CIDX[c], d, d)) or "")
            time.sleep(0.4)
        try:
            r.cmd("quit")
        except Exception:
            pass
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=ET.NO_WINDOW)
        open(cfgp, "w").write("// rcon password removed after the run\n")
        shutil.rmtree(cdir, ignore_errors=True)
    txt = (open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else "") + "\n" + "\n".join(resp)
    out = {}
    for m in re.finditer(r"BUCKET (\S+)\|(\S+) (\S+) (-?\d+)", txt):
        out.setdefault(m.group(1), {})[m.group(2)] = [m.group(3), int(m.group(4))]
    os.makedirs(os.path.join(ROOT, "analysis"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "analysis", "weapon_buckets_5205.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
