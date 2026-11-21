"""Slot rule (user bug 2026-11-20: "customslop weapons preventing slot 1/2 picking, eg the sniper's
shotgun and sten customslop weapons given to his primary slot"; tf2cc learned it 2026-11-17):
in TF2C 5205 an item's item_class must NATIVELY belong to the loadout slot it is given to, for every
class it is given to. A cross-slot class makes the client's slot keys stop switching (the server is
fine, so only the client shows it).

Rule (revised 2026-11-20 after the user's report on 26061/26042/26053/26080): the client's slot keys
follow the weapon ENTITY's script bucket (CTFWeaponBase::GetSlot), and 5205 creates a per-class
entity for some item classes (tf_weapon_shotgun -> _hwg / _pyro / _soldier / _primary). An item is
OK in a loadout slot for a class iff the bucket of the entity 5205 creates for that class (measured
in the engine: bucketprobe.py -> analysis/weapon_buckets_5205.json) equals the bucket of the class's
STOCK weapon(s) in that slot (stock items of the base items_game: used_by_classes "1" -> item_slot,
a slot name -> that slot). A mismatch puts two weapons on one slot key (e.g. a Sniper SMG in primary
next to the stock SMG: both bucket 1, key 1 empty). Spy's revolver (secondary, bucket 0) is native.

  native_slots(cls, item_class) -> set of slots
  ok(cls, item_class, slot)     -> bool
  fix(fs, class_slots, item_class, family) -> an item_class that passes the slot rule AND the taunt
      rule for every (class, slot), or None. Candidates in order: the donor's own class, the taunt
      equivalents (generic shotgun/pistol, the class's stock melee, saxxy), then stock item classes
      native to that slot for every class in the SAME weapon family (hitscan stays hitscan).
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import taunts  # noqa: E402

_T = None
SLOTS = ("primary", "secondary", "melee")


def table():
    global _T
    if _T is None:
        from generate import BASE_SCHEMA, load_schema      # (generate puts kv on the path)
        import kv
        import labels
        st = load_schema(BASE_SCHEMA)
        pf = {k.lower(): b for k, b in st.get("prefabs").blocks()} if st.get("prefabs") else {}
        t = collections.defaultdict(set)
        for k, it in st.get("items").blocks():
            if not k.isdigit():
                continue
            ic = labels._eff(it, "item_class", pf)
            slot = labels._eff(it, "item_slot", pf)
            ubc = labels._eff(it, "used_by_classes", pf)
            if not ic or not slot or not isinstance(ubc, kv.KV):
                continue
            for c, v in ubc.pairs:
                t[(c.capitalize(), ic.lower())].add((slot if v == "1" else v).lower())
        _T = dict(t)
    return _T


_B = None


def buckets():
    """{item_class: {class: [entity, bucket]}} measured in the 5205 engine (bucketprobe.py)."""
    global _B
    if _B is None:
        import json
        _B = json.load(open(os.path.join(os.path.dirname(HERE), "analysis", "weapon_buckets_5205.json")))
    return _B


_SB, _FS = {}, None


def _script_bucket(entity):
    global _FS
    if entity in _SB:
        return _SB[entity]
    import re
    import vfs
    _FS = _FS or vfs.VFS()
    d = _FS.read("scripts/%s.txt" % entity)
    m = re.search(rb'"?bucket"?\s+"?(\d+)', d or b"")
    _SB[entity] = int(m.group(1)) if m else None
    return _SB[entity]


def bucket(cls, item_class):
    """The weapon script bucket (= the client's slot key) of the entity 5205 creates for this class."""
    ic = (item_class or "").lower()
    e = buckets().get(ic, {}).get(cls)
    if e and e[1] >= 0:
        return e[1]
    ent = next((v[0] for v in buckets().get(ic, {}).values() if v[1] >= 0), None) or taunts.entity(ic, cls)
    return _script_bucket(ent)


_STB = {}


def stock_buckets(cls, slot):
    """Buckets the class's STOCK items in this loadout slot have (native table x engine buckets)."""
    if (cls, slot) in _STB:
        return _STB[(cls, slot)]
    out = set()
    for (c, ic), slots in table().items():
        if c == cls and slot in slots:
            b = bucket(cls, ic)
            if b is not None:
                out.add(b)
    _STB[(cls, slot)] = out
    return out


def native_slots(cls, item_class):
    """Loadout slots where this item_class's bucket matches the class's stock weapon bucket."""
    b = bucket(cls, item_class)
    return {s for s in SLOTS if b is not None and b in stock_buckets(cls, s)}


def ok(cls, item_class, slot):
    return (slot or "").lower() in native_slots(cls, item_class)


def slot_for(classes, cls, item_slot):
    """effective loadout slot of the item for one class (used_by_classes value or item_slot)."""
    v = classes.get(cls, "1") if isinstance(classes, dict) else "1"
    return (item_slot if v in ("1", "", None) else v).lower()


def fix(fs, class_slots, item_class, family):
    """class_slots: {class: effective slot}. -> item_class passing slot + taunt for all, or None."""
    from generate import FAMILY
    cl = [c for c in class_slots if c in taunts.CLASS_INDEX]
    cands = [item_class]
    t = taunts.fix_item_class(fs, cl, item_class, family)
    if t:
        cands.append(t)
    ic = (item_class or "").lower()
    for generic in ("tf_weapon_shotgun", "tf_weapon_pistol"):
        if ic.startswith(generic):
            cands.append(generic)
    if family == "melee":
        cands += [taunts.MELEE.get(c) for c in cl] + ["saxxy"]
    fam_ics = sorted(FAMILY.get(family, ()))
    cands += [x for x in fam_ics if x not in cands]
    for c_ in cands:
        if c_ and all(ok(c, c_, class_slots[c]) and taunts.ok(fs, c, c_) for c in cl):
            return c_
    return None
