"""Engine check for the slot rule (slotrule.py): for each slot-fixed live weapon, a BEFORE item (old
item_class / slot / classes) and an AFTER item (fixed), on an isolated LAN server (enginetest copy,
127.0.0.1, per-run RCON password, no client, no Steam, IDLE, minimised console). A bot of each class
gets the item; logged per weapon it holds: GetSlot() (the weapon script bucket = the client's slot
key) and classname. Broken = two held weapons share a bucket (the client's slot key can only reach
one of them) or a Weapon_Switch to a held weapon does not make it active. The client-side key
symptom itself cannot be proven without a client: GenerateAndWearItem equips by the weapon's
bucket (the item replaced the stock SMG even when its item_slot said primary), whereas a real
loadout puts a primary-slot item NEXT TO the stock secondary - two bucket-1 weapons, the reported
bug. Writes slottest_result.json.

  python -I slottest.py
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
import slopqueue as Q  # noqa: E402

PORT = 27983
BOT = {"Scout": "scout", "Soldier": "soldier", "Pyro": "pyro", "Demoman": "demoman", "Heavy": "heavyweapons",
       "Engineer": "engineer", "Medic": "medic", "Sniper": "sniper", "Spy": "spy"}
CIDX = {"Scout": 1, "Sniper": 2, "Soldier": 3, "Demoman": 4, "Medic": 5, "Heavy": 6, "Pyro": 7, "Spy": 8, "Engineer": 9}

NUT = r'''
function ST_Log(s) { printl("SLOTTEST " + s); }
function ST_Bot(c) {
    local p = null;
    while (p = Entities.FindByClassname(p, "player")) if (p.GetPlayerClass() == c) return p;
    return null;
}
function ST_Run(tag, c, name, di) {
    local p = ST_Bot(c);
    if (!p) { ST_Log(tag + " nobot"); return; }
    p.ForceRespawn();
    p.GenerateAndWearItem(name);
    local s = "";
    local mine = null;
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (!w) continue;
        local d = NetProps.GetPropInt(w, "m_AttributeManager.m_Item.m_iItemDefinitionIndex");
        if (d == di) mine = w;
        s += " " + w.GetSlot() + ":" + w.GetClassname() + ":" + d;
    }
    local sw = "";
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (!w || w.GetSlot() > 2) continue;
        p.Weapon_Switch(w);
        local a = p.GetActiveWeapon();
        sw += " " + w.GetSlot() + (a == w ? "=ok" : "=FAIL");
    }
    ST_Log(tag + " held" + s + " | switch" + sw + " | mine " + (mine ? mine.GetSlot() : -1));
}
'''


def main():
    st = Q.load_state(Q.cfg())
    rows = json.load(open(os.path.join(ROOT, "slotfix_result_dryrun.json")))
    cases, frag, di = [], "", 29950
    for r in rows:
        if not r.get("changed"):
            continue
        w = st["weapons"][str(r["defindex"])]
        key, it = kv.parse(open(os.path.join(ROOT, w["dir"], "item.txt.pre_slot")
                                if os.path.exists(os.path.join(ROOT, w["dir"], "item.txt.pre_slot"))
                                else os.path.join(ROOT, w["dir"], "item.txt"), encoding="utf-8").read())[0].pairs[0]
        for tag, spec in (("before", r["before"]), ("after", r["plan"])):
            pairs = []
            for k_, v_ in it.pairs:
                if k_ in ("attributes", "used_by_classes", "item_class", "item_slot", "name"):
                    continue
                pairs.append((k_, v_))
            pairs += [("name", "customslop_slottest_%d" % di), ("item_class", spec["item_class"]),
                      ("item_slot", spec["slot"]), ("used_by_classes", kv.KV(list(spec["classes"].items())))]
            frag += '"%d"\n{\n%s}\n' % (di, kv.dump(kv.KV(pairs), 1))
            for c in spec["classes"]:
                cases.append(dict(defindex=r["defindex"], test_id=di, tag=tag, cls=c, item_class=spec["item_class"],
                                  slot=spec["slot"]))
            di += 1
    base_rel, text = A.base_schema(ET.LIVE)
    text = text.decode("utf-8", errors="replace")
    secs, _ = A._blocks(text)
    at_ = secs["items"][1] - 1
    schema = (text[:at_] + frag + text[at_:]).encode("utf-8")
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write(schema)
    # the live models/materials of these weapons, so GenerateAndWearItem finds the model
    for r in rows:
        if r.get("changed"):
            src = os.path.join(ROOT, st["weapons"][str(r["defindex"])]["dir"], "files")
            if os.path.isdir(src):
                shutil.copytree(src, cdir, dirs_exist_ok=True)
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_slottest.nut"), "w").write(NUT)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_slottest.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_waitingforplayers_cancel 1",
                                     "mp_teams_unbalance_limit 0", "mp_autoteambalance 0", 'rcon_password "%s"' % pw,
                                     "script_execute customslop_slottest", ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "12", "+servercfgfile", "customslop_slottest.cfg", "+map", "ctf_2fort"]
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
        resp.append(r.cmd("script_execute customslop_slottest") or "")
        for c in sorted({x["cls"] for x in cases}):
            r.cmd("tf_bot_add 1 %s red" % BOT[c])
        time.sleep(10)
        for x in cases:
            resp.append(r.cmd('script ST_Run("%d_%s_%s", %d, "customslop_slottest_%d", %d)' % (
                x["defindex"], x["tag"], x["cls"], CIDX[x["cls"]], x["test_id"], x["test_id"])) or "")
            time.sleep(1.5)
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
    out = []
    for l in txt.splitlines():
        m = re.search(r"SLOTTEST (\S+) held(.*?) \| switch(.*?) \| mine (-?\d+)", l)
        if not m:
            continue
        held = [h.split(":") for h in m.group(2).split()]
        buckets = [int(h[0]) for h in held if int(h[0]) <= 2]
        out.append(dict(case=m.group(1), held=[":".join(h) for h in held], switch=m.group(3).strip(),
                        mine_bucket=int(m.group(4)),
                        bucket_collision=len(buckets) != len(set(buckets)), switch_fail="FAIL" in m.group(3)))
    res = dict(cases=out, errors=[l for l in txt.splitlines() if "AN ERROR HAS OCCURRED" in l][:10])
    json.dump(res, open(os.path.join(ROOT, "slottest_result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
