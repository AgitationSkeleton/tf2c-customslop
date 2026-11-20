"""Which (player class, item) combinations can taunt in TF2 Classified 5205.

How 5205 picks a weapon taunt (server/tf/tf_player.cpp CTFPlayer::Taunt + ModifyOrAppendCriteria):
the TLK_PLAYER_TAUNT response rules in scripts/talker/*.txt are matched on "playerclass" and
"playerweapon" = the ACTIVE weapon entity's classname, i.e. the item's item_class after
TranslateWeaponEntForClass (tf_shareddefs.cpp: "tf_weapon_shotgun" -> _soldier / _hwg / _pyro /
_primary per class, "saxxy" -> the class's stock melee, ...). A few rules match "item_name" (the
schema name, e.g. "Coilgun") instead. There is NO default rule: an item whose entity class has no
rule for the wielding class cannot taunt at all.

  ok(fs, cls, item_class)       can this class taunt with an item of this item_class?
  entity(item_class, cls)       the entity classname 5205 creates
  melee_for(fs, cls)            an item_class whose melee taunts for this class
"""
import re

CLASS_INDEX = {"Scout": 1, "Sniper": 2, "Soldier": 3, "Demoman": 4, "Medic": 5, "Heavy": 6, "Pyro": 7, "Spy": 8,
               "Engineer": 9, "Civilian": 10}
_ORDER = ["Scout", "Sniper", "Soldier", "Demoman", "Medic", "Heavy", "Pyro", "Spy", "Engineer", "Civilian"]
# TranslateWeaponEntForClass table (TF2C game source, shared/tf/tf_shareddefs.cpp)
TRANSLATE = {
    "tf_weapon_shotgun": ["tf_weapon_shotgun_primary", "tf_weapon_shotgun_primary", "tf_weapon_shotgun_soldier",
                          "tf_weapon_shotgun_primary", "tf_weapon_shotgun_primary", "tf_weapon_shotgun_hwg",
                          "tf_weapon_shotgun_pyro", "tf_weapon_shotgun_primary", "tf_weapon_shotgun_primary",
                          "tf_weapon_shotgun_primary"],
    "tf_weapon_pistol": ["tf_weapon_pistol_scout"] + ["tf_weapon_pistol"] * 9,
    "tf_weapon_shovel": ["tf_weapon_shovel"] * 3 + ["tf_weapon_bottle"] + ["tf_weapon_shovel"] * 6,
    "tf_weapon_bottle": ["tf_weapon_bottle"] * 2 + ["tf_weapon_shovel"] + ["tf_weapon_bottle"] * 7,
    "saxxy": ["tf_weapon_bat", "tf_weapon_club", "tf_weapon_shovel", "tf_weapon_bottle", "tf_weapon_bonesaw",
              "tf_weapon_fireaxe", "tf_weapon_fireaxe", "tf_weapon_knife", "tf_weapon_wrench", "tf2c_weapon_umbrella"],
    "tf_weapon_revolver": ["tf_weapon_revolver"] * 8 + ["tf_weapon_revolver_secondary", "tf_weapon_revolver"],
}
_RULES = None


def entity(item_class, cls):
    t = TRANSLATE.get((item_class or "").lower())
    return t[_ORDER.index(cls)] if t and cls in _ORDER else (item_class or "").lower()


def rules(fs):
    """{class: set of entity classnames with a (non-Halloween) taunt rule} from the installed talker files."""
    global _RULES
    if _RULES is not None:
        return _RULES
    import os
    import vfs
    texts = {}
    for kind, path in vfs.DEFAULT_ORDER:
        if kind == "vpk" and os.path.exists(path):
            for n in vfs.VPK(path).ents:
                if n.startswith("scripts/talker/") and n not in texts:
                    b = fs.read(n)
                    if b:
                        texts[n] = b.decode("latin-1")
    crit = {}
    for t in texts.values():
        for m in re.finditer(r'(?im)^\s*criterion\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]*)"', t):
            crit.setdefault(m.group(1).lower(), (m.group(2).lower(), m.group(3)))
    out = {}
    for t in texts.values():
        for m in re.finditer(r'(?is)rule\s+(\S+)\s*\{(.*?)\}', t):
            cr = re.search(r'criteria\s+([^\n]+)', m.group(2))
            if not cr:
                continue
            names = [c.lower() for c in cr.group(1).split()]
            if "conceptplayertaunt" not in names or "ishalloweentaunt" in names:
                continue
            cs = [crit.get(c, ("?", c)) for c in names]
            cl = [v for k, v in cs if k == "playerclass"]
            pw = [v.lower() for k, v in cs if k == "playerweapon"]
            if cl and pw:
                out.setdefault(cl[0], set()).update(pw)
    _RULES = out
    return out


def ok(fs, cls, item_class):
    return entity(item_class, cls) in rules(fs).get(cls, set())


MELEE = {"Scout": "tf_weapon_bat", "Sniper": "tf_weapon_club", "Soldier": "tf_weapon_shovel", "Demoman": "tf_weapon_bottle",
         "Medic": "tf_weapon_bonesaw", "Heavy": "tf_weapon_fists", "Pyro": "tf_weapon_fireaxe", "Spy": "tf_weapon_knife",
         "Engineer": "tf_weapon_wrench", "Civilian": "tf2c_weapon_umbrella"}


def melee_for(fs, cls):
    """An item_class whose melee taunt this class has (its stock melee; Heavy: fists)."""
    ic = MELEE.get(cls)
    return ic if ic and ok(fs, cls, ic) else None


def fix_item_class(fs, classes, item_class, family):
    """A behaviour-equivalent item_class that lets EVERY given class taunt, or None. Shotgun and pistol
    variants become the generic class (5205 translates it per class); melee becomes the class's own
    stock melee (single class) or "saxxy" (several classes, translated per class)."""
    cl = [c for c in classes if c in _ORDER]
    if all(ok(fs, c, item_class) for c in cl):
        return item_class
    ic = (item_class or "").lower()
    for generic in ("tf_weapon_shotgun", "tf_weapon_pistol"):
        if ic.startswith(generic) and all(ok(fs, c, generic) for c in cl):
            return generic
    if family == "melee":
        if len(cl) == 1 and melee_for(fs, cl[0]):
            return melee_for(fs, cl[0])
        if all(ok(fs, c, "saxxy") for c in cl):
            return "saxxy"
    return None
