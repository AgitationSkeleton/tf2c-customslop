"""Where does an attribute act? Scope of every attribute class from the TF2C game source's
CALL_ATTRIB_HOOK_* call sites (user bug: "slow holster/draw time persists between lives/weapon
changes" - e.g. mult_deploy_time is read on the PLAYER, so it slows every weapon the wearer draws,
while mult_single_wep_deploy_time is read on the weapon itself).

Per call site:
  weapon  CALL_ATTRIB_HOOK_X(value, cls) inside weapon code, or ..._ON_OTHER(<a specific weapon>)
  active  ..._ON_OTHER(<the ACTIVE weapon>) - only while the item is out
  wearer  a hook on the player / owner / attacker / victim / builder aggregate: every item the
          player has EQUIPPED contributes, active or not -> acts across weapon switches and lives
  other   anything else (buildings, projectiles, game rules) - reported, treated as not safe
Per attribute class: safe iff every call site is weapon/active. Classes with no call site in the
source are "unverified" (no evidence they do anything in 5205).
Writes analysis/attribute_scope_5205.json.

  python -I attrscope.py [--src <tf2c src/game>]
"""
import argparse
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = __import__("cspaths").opt("tf2c_source_dir")   # TF2C source "src/game" folder (config)
OUT = os.path.join(ROOT, "analysis", "attribute_scope_5205.json")

CALL = re.compile(r"CALL_ATTRIB_HOOK_(FLOAT|INT|STRING|ENUM)(_ON_OTHER)?\s*\(")
ACTIVE = re.compile(r"Active(TF)?Weapon|pActiveWe|pActive\b|GetActiveWeapon|m_hActiveWeapon", re.I)
WEAPON = re.compile(r"weapon|pWpn|\bpWep|Launcher|pGun|pMelee|pMedigun|pKnife|pBow|pFlame|pItem\b|pWearable|this\b", re.I)
WEARER = re.compile(r"Player|Owner|Attacker|Victim|Outer|Healer|Patient|Target|Builder|pTF\b|pEntity|pOther|Pyro|Scorer|"
                    r"Thrower|pHealed|pRecipient|pCarrier|pSpy|pMedic", re.I)
WEAPON_FILE = re.compile(r"^tf_weapon|^tf_weaponbase|^tf_wearable_weapon|^tf_weapon_")
PLAYER_FILE = re.compile(r"^tf_player|^tf_gamerules|^tf_gamemovement")


def args_of(text, start):
    depth, i, cur, out = 1, start, "", []
    while i < len(text) and depth:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append(cur.strip())
                break
        if ch == "," and depth == 1:
            out.append(cur.strip())
            cur = ""
        elif depth >= 1:
            cur += ch
        i += 1
    return out


LINK = re.compile(r"LINK_ENTITY_TO_CLASS\(\s*(\w+)\s*,|CREATE_SIMPLE_WEAPON_TABLE\(\s*\w+\s*,\s*(\w+)\s*\)")
BASE_FILE = re.compile(r"^tf_weaponbase(_gun|_melee|_rocket|_grenadeproj|_nail)?\.(cpp|h)$|^tf_projectile|^tf_weapon_grenade_|"
                       r"^tf_weapon_parse|^tf_fx_shared")


def scan(src):
    sites = collections.defaultdict(list)
    links = {}
    for dp, _, fs in os.walk(src):
        for f in fs:
            if not f.endswith((".cpp", ".h")):
                continue
            p = os.path.join(dp, f)
            txt = open(p, encoding="latin-1").read()
            for lm in LINK.finditer(txt):
                links.setdefault((lm.group(1) or lm.group(2)).lower(), f)
            for m in CALL.finditer(txt):
                a = args_of(txt, m.end())
                if len(a) < 2:
                    continue
                cls = a[-1].strip()
                if not re.match(r"^\w+$", cls):
                    continue
                if re.search(r"animstate", f, re.I):
                    continue                     # animation playback speed only (visual), not gameplay
                if m.group(2) and a[0].strip() in ("this", "this->GetOwner()") and not WEAPON_FILE.search(f):
                    other = a[0]
                    sc = "wearer" if PLAYER_FILE.search(f) or "Owner" in other else "other"
                elif m.group(2):
                    other = a[0]
                    if ACTIVE.search(other):
                        sc = "active"
                    elif WEAPON.search(other) and not re.search(r"Owner|Player", other):
                        sc = "weapon"
                    elif WEARER.search(other):
                        sc = "wearer"
                    else:
                        sc = "other"
                else:
                    other = "this"
                    sc = "weapon" if WEAPON_FILE.search(f) else ("wearer" if PLAYER_FILE.search(f) else "other")
                line = txt.count("\n", 0, m.start()) + 1
                sites[cls].append(dict(file=f, line=line, scope=sc, other=other[:60]))
    return sites, links


def own_file(item_class, links):
    """Source file of an item class: its weapon-table registration, else tf_weapon_<stem>.cpp
    (5205's tf2c_weapon_* classes are tf_weapon_* in the 2024 source)."""
    ic = (item_class or "").lower()
    stem = re.sub(r"^tf2?c?_weapon_", "", ic)
    return links.get(ic) or links.get("tf_weapon_" + stem) or "tf_weapon_%s.cpp" % stem


def works_on(info, item_class, links):
    """Does a SAFE attribute act on an item of this class? A site works generically if it is read
    for the active weapon, or on the weapon in shared/base code (weapon base classes, projectiles,
    damage rules); a site in one weapon's own file (tf_weapon_invis.cpp) only for that class."""
    if not info or info["verdict"] != "safe":
        return False
    own = own_file(item_class, links)
    for st in info["sites"]:
        f = st["file"]
        if st["scope"] == "active":
            return True
        if not f.startswith("tf_weapon") or BASE_FILE.search(f):
            return True
        if own and f.rsplit(".", 1)[0] == own.rsplit(".", 1)[0]:
            return True
    return False


def load():
    d = json.load(open(OUT))
    return d["classes"], d["links"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()
    sites, links = scan(a.src)
    out = {}
    for cls, ss in sites.items():
        scopes = sorted({s["scope"] for s in ss})
        verdict = "safe" if set(scopes) <= {"weapon", "active"} else ("persists" if "wearer" in scopes else "other")
        out[cls] = dict(verdict=verdict, scopes=scopes, sites=ss[:40])
    json.dump(dict(classes=out, links=links), open(OUT, "w"), indent=1)
    c = collections.Counter(v["verdict"] for v in out.values())
    print("attribute classes with call sites:", len(out), dict(c))


if __name__ == "__main__":
    main()
