"""Engine safety test for the WIDENED value ranges (standing rule, user 2026-11-20: ridiculous values
in either direction are intended; only crash/engine safety may limit a range).

For every whitelisted definition (attreffect.SPEC) and both ends of its range (the generic roller's
safety bounds for definitions without a SPEC range), a test item = a stock weapon of a class it
works for + that ONE attribute at that extreme value. An isolated LAN server (enginetest copy,
127.0.0.1, per-run RCON password, no client, no Steam, IDLE priority, minimised console) runs
ctf_2fort with bots of every class; every few seconds each bot is handed the next extreme item of
its class and the bots fight. Pass = the server stays up and answers RCON for the whole run, every
item was handed out, and the console has no crash / overflow / edict / schema error.
Writes extremetest_result.json.

  python -I extremetest.py [--minutes 8]
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
import attreffect as E  # noqa: E402
import attrscope  # noqa: E402
import enginetest as ET  # noqa: E402
import kv  # noqa: E402
import pipeline as PL  # noqa: E402
import relevance  # noqa: E402
from generate import BASE_SCHEMA, FAMILY, load_schema  # noqa: E402

PORT = 27985
FIRST_ID = 29000
# stock bases per class (5205 defindex): primary / secondary / melee
BASES = {"Scout": [13, 23, 0], "Soldier": [18, 10, 6], "Pyro": [21, 12, 2], "Demoman": [19, 20, 1],
         "Heavy": [15, 11, 5], "Engineer": [9, 22, 7], "Medic": [17, 29, 8], "Sniper": [14, 16, 3],
         "Spy": [24, 4]}
BOTCLASS = {"Scout": "scout", "Soldier": "soldier", "Pyro": "pyro", "Demoman": "demoman", "Heavy": "heavyweapons",
            "Engineer": "engineer", "Medic": "medic", "Sniper": "sniper", "Spy": "spy"}
BAD = re.compile(r"crash|Reliable buffer overflow|SZ_GetSpace|ED_Alloc|no free edicts|Item schema load failed|"
                 r"KeyValues Error|Host_Error|Segmentation|exception|overflowed", re.I)


def extremes(p):
    s = E.SPEC.get(p["name"])
    if s and s["v"]:
        lo, hi = s["v"]
        return sorted({lo, hi})
    if p["direction"] == "flag":
        return [1]
    if p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage"):
        lo, hi = PL.safety_range(p)
        return [lo, hi]
    return []


def build():
    st = load_schema(BASE_SCHEMA)
    items = dict(st.get("items").blocks())
    pf = {k.lower(): b for k, b in st.get("prefabs").blocks()} if st.get("prefabs") else {}
    import labels
    cl, ln = attrscope.load()
    pool = [p for p in json.load(open(os.path.join(ROOT, "analysis", "attribute_pool_5205.json")))
            if p["disposition"] != "excluded" and p["name"] in E.SPEC and not p["hidden"] and p.get("desc_text")]
    cases, frag, di = [], "", FIRST_ID
    per_class = {}
    for p in pool:
        for v in extremes(p):
            okb = []
            for cls_, ids in BASES.items():
                for bid in ids:
                    b = items.get(str(bid))
                    if b is None:
                        continue
                    ic = labels._eff(b, "item_class", pf)
                    slot = labels._eff(b, "item_slot", pf)
                    fam = next((f for f, ics in FAMILY.items() if ic in ics), None)
                    prov = relevance.provides(ic or "", fam, [cls_], slot)
                    if E.allowed(p, ic) and attrscope.works_on(cl.get(p["cls"]), ic, ln)                             and relevance.needs(p, None) in prov:
                        okb.append((cls_, bid, b, ic, slot))
            # spread the items over the classes so every bot cycles through its list during the run
            base = min(okb, key=lambda x: (per_class.get(x[0], 0), x[1])) if okb else None
            if base:
                per_class[base[0]] = per_class.get(base[0], 0) + 1
            if not base:
                continue
            cls_, bid, b, ic, slot = base
            it = kv.KV()
            it.add("name", "customslop_extreme_%d" % di)
            for key in ("item_class", "item_slot", "item_quality", "model_player", "model_world", "attach_to_hands",
                        "anim_slot", "item_type_name", "item_name"):
                vv = labels._eff(b, key, pf)
                if vv is not None:
                    it.add(key, vv)
            ubc = kv.KV()
            ubc.add(cls_, "1")
            it.add("used_by_classes", ubc)
            at, bb = kv.KV(), kv.KV()
            bb.add("attribute_class", p["cls"])
            bb.add("value", str(v))
            at.add(p["name"], bb)
            it.add("attributes", at)
            frag += '"%d"\n{\n%s}\n' % (di, kv.dump(it, 1))
            cases.append(dict(defindex=di, cls=cls_, base=bid, item_class=ic, slot=slot, attribute=p["name"],
                              attr_class=p["cls"], value=v))
            di += 1
    base_rel, text = A.base_schema(ET.LIVE)
    text = text.decode("utf-8", errors="replace")
    secs, _ = A._blocks(text)
    at_ = secs["items"][1] - 1
    return (text[:at_] + frag + text[at_:]).encode("utf-8"), cases


NUT_HEAD = r'''
function EX_Log(s) { printl("EXTREME " + s); }
function EX_Slot(p, s) {
    for (local i = 0; i < 48; i++) {
        local w = NetProps.GetPropEntityArray(p, "m_hMyWeapons", i);
        if (w && w.GetSlot() == s) return w;
    }
    return null;
}
::EX_I <- {};
function EX_Round() {
    local p = null;
    while (p = Entities.FindByClassname(p, "player")) {
        if (!p.IsAlive()) continue;
        local c = p.GetPlayerClass();
        if (!(c in EX_ITEMS)) continue;
        local L = EX_ITEMS[c];
        local k = p.entindex();
        if (!(k in EX_I)) EX_I[k] <- 0;
        local e = L[EX_I[k] % L.len()];
        EX_I[k] = EX_I[k] + 1;
        p.GenerateAndWearItem("customslop_extreme_" + e[0]);
        local w = EX_Slot(p, e[1]);
        if (w) p.Weapon_Switch(w);
        local got = w ? NetProps.GetPropInt(w, "m_AttributeManager.m_Item.m_iItemDefinitionIndex") : -1;
        EX_Log("gave " + e[0] + " to " + c + " held " + got);
    }
}
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=8)
    a = ap.parse_args()
    schema, cases = build()
    cdir = os.path.join(ET.GAME, "custom", "customslop_test")
    shutil.rmtree(cdir, ignore_errors=True)
    os.makedirs(os.path.join(cdir, "scripts", "items"))
    open(os.path.join(cdir, "scripts", "items", "custom_items_game.txt"), "wb").write(schema)
    CLSIDX = {"Scout": 1, "Sniper": 2, "Soldier": 3, "Demoman": 4, "Medic": 5, "Heavy": 6, "Pyro": 7, "Spy": 8, "Engineer": 9}
    SLOTN = {"primary": 0, "secondary": 1, "melee": 2, "pda": 3, "pda2": 4, "building": 5}
    by = {}
    for c in cases:
        by.setdefault(CLSIDX[c["cls"]], []).append("[%d, %d]" % (c["defindex"], SLOTN.get((c["slot"] or "primary").lower(), 0)))
    nut = NUT_HEAD + "::EX_ITEMS <- {\n" + ",\n".join("[%d] = [%s]" % (k, ", ".join(v)) for k, v in sorted(by.items())) + "\n};\n"
    os.makedirs(os.path.join(ET.GAME, "scripts", "vscripts"), exist_ok=True)
    open(os.path.join(ET.GAME, "scripts", "vscripts", "customslop_extremetest.nut"), "w").write(nut)
    pw = secrets.token_hex(12)
    cfgp = os.path.join(ET.GAME, "cfg", "customslop_extremetest.cfg")
    open(cfgp, "w").write("\n".join(["sv_lan 1", "sv_cheats 1", "tf_allow_server_hibernation 0", "tf_bot_quota 0",
                                     "tf_bot_join_after_player 0", "mp_timelimit 0", "mp_winlimit 0",
                                     "mp_waitingforplayers_cancel 1", "mp_teams_unbalance_limit 0",
                                     "mp_autoteambalance 0", 'rcon_password "%s"' % pw,
                                     "script_execute customslop_extremetest", ""]))
    log = os.path.join(ET.GAME, "console.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [os.path.join(ET.ET, "srcds_win64.exe"), "-game", ET.GAME, "-console", "-insecure", "-nomaster", "-nocrashdialog",
           "-condebug", "-usercon", "-nohltv", "+sv_lan", "1", "+ip", "127.0.0.1", "+hostport", str(PORT), "+clientport",
           str(PORT - 1), "+tv_enable", "0", "+maxplayers", "20", "+servercfgfile", "customslop_extremetest.cfg",
           "+map", "ctf_2fort"]
    p = subprocess.Popen(cmd, cwd=ET.ET, creationflags=subprocess.CREATE_NEW_CONSOLE | 0x40,   # IDLE priority
                         startupinfo=ET.quiet_console())                                  # minimised, no focus
    res = dict(items=len(cases), cases=cases, alive_checks=0, alive_failures=0, died=False)
    resp = []                     # script printl output comes back in the RCON responses
    try:
        t0 = time.time()
        while not (os.path.exists(log) and "SV_ActivateServer" in open(log, encoding="utf-8", errors="replace").read()):
            if p.poll() is not None or time.time() - t0 > 180:
                raise RuntimeError("server did not start")
            time.sleep(2)
        time.sleep(4)
        r = ET.Rcon(PORT, pw)
        r.cmd("sv_cheats 1")
        resp.append(r.cmd("script_execute customslop_extremetest") or "")
        for team in ("red", "blue"):
            for c in BOTCLASS.values():
                r.cmd("tf_bot_add 1 %s %s" % (c, team))
        time.sleep(15)
        end = time.time() + a.minutes * 60
        while time.time() < end:
            if p.poll() is not None:
                res["died"] = True
                break
            try:
                resp.append(r.cmd("script EX_Round()") or "")
                res["alive_checks"] += 1
            except Exception:
                res["alive_failures"] += 1
                try:
                    r = ET.Rcon(PORT, pw)
                except Exception:
                    pass
            time.sleep(4)
        res["exit_code_during_run"] = p.poll()
        try:
            res["final_status"] = (r.cmd("status") or "")[:200]
            r.cmd("quit")
        except Exception as e:
            res["final_status"] = "rcon failed: %r" % e
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=ET.NO_WINDOW)
        open(cfgp, "w").write("// rcon password removed after the run\n")
        shutil.rmtree(cdir, ignore_errors=True)
    txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    txt += chr(10) + chr(10).join(x for x in resp if isinstance(x, str))
    res["script_errors"] = [l for l in txt.splitlines() if "AN ERROR HAS OCCURRED" in l or "wrong number" in l][:10]
    gave = re.findall(r"EXTREME gave (\d+) to \d+ held (-?\d+)", txt)
    res["handed_out"] = len({g for g, _ in gave})
    res["held_ok"] = len({g for g, h in gave if g == h})
    res["never_held"] = sorted({int(c["defindex"]) for c in cases} - {int(g) for g, h in gave if g == h})[:80]
    res["bad_lines"] = [l for l in txt.splitlines() if BAD.search(l)][:40]
    res["ok"] = not res["died"] and not res["alive_failures"] and not res["bad_lines"] and res["exit_code_during_run"] is None
    json.dump(res, open(os.path.join(ROOT, "extremetest_result.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "cases"}, indent=1))


if __name__ == "__main__":
    main()
