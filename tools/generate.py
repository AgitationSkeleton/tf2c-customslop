"""CustomSlop generator prototype (stats / names / class fit / schema emission / rotation).

Offline and read-only on inputs. Writes into <research>/gen/:
  state.json                  rolling history (defindex, date, name, classes, assets) - the
                              rotation source of truth; defindexes are never reused
  customslop_items.txt        the CustomSlop "items" + "attributes" block (KeyValues)
  custom_items_game.txt       merged schema: base #base + tf2cc/AF schema + CustomSlop block
  today.json                  what the plugin / webhook / ad need (names, classes, icons)
  customslop_schema_report.json  validation results

usage: python -I generate.py [--date 2026-11-16] [--count 3] [--cap 50] [--seed N]
         [--merge-from <existing custom_items_game.txt>] [--ill-fit 0.15] [--multi 0.1]
"""
import argparse
import datetime as dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths as P  # noqa: E402
import kv  # noqa: E402
import names  # noqa: E402

BASE_SCHEMA = P.data("items_game.txt")
AF_SCHEMA = P.af_schema()
TF2CC_SCHEMA = os.path.join(P.opt("tf2cc_staging_dir") or "", "scripts", "items", "custom_items_game.txt")

DEFINDEX_FIRST, DEFINDEX_LAST = 26000, 29999      # < 30099 (tf2cc) and > 17519 (AF); short-safe
CS_ATTR_FIRST = 25900                              # CustomSlop VScript attributes
CLASSES = ["Scout", "Soldier", "Pyro", "Demoman", "Heavy", "Engineer", "Medic", "Sniper", "Spy", "Civilian"]
# loadout slots that exist per class (a base item exists there on 5205; Civilian: melee only by default)
CLASS_SLOTS = {"Scout": ["primary", "secondary", "melee"], "Soldier": ["primary", "secondary", "melee"],
               "Pyro": ["primary", "secondary", "melee"], "Demoman": ["primary", "secondary", "melee"],
               "Heavy": ["primary", "secondary", "melee"], "Engineer": ["primary", "secondary", "melee"],
               "Medic": ["primary", "secondary", "melee"], "Sniper": ["primary", "secondary", "melee"],
               "Spy": ["secondary", "melee"], "Civilian": ["melee"]}

FAMILY = {
    "hitscan": {"tf_weapon_scattergun", "tf_weapon_shotgun", "tf_weapon_shotgun_primary", "tf_weapon_shotgun_soldier",
                "tf_weapon_pistol", "tf_weapon_smg", "tf_weapon_revolver", "tf_weapon_sniperrifle", "tf_weapon_minigun",
                "tf2c_weapon_hunting_revolver", "tf2c_weapon_doubleshotgun", "tf2c_weapon_aagun"},
    "rocket": {"tf_weapon_rocketlauncher"},
    "grenade": {"tf_weapon_grenadelauncher", "tf_weapon_pipebomblauncher", "tf2c_weapon_cyclops"},
    "projectile": {"tf2c_weapon_nailgun", "tf_weapon_syringegun_medic", "tf2c_weapon_coilgun", "tf_weapon_flaregun",
                   "tf_weapon_compound_bow", "tf2c_weapon_tranq"},
    "flame": {"tf_weapon_flamethrower"},
    "melee": {"tf_weapon_bat", "tf_weapon_bottle", "tf_weapon_fireaxe", "tf_weapon_club", "tf_weapon_knife",
              "tf_weapon_fists", "tf_weapon_shovel", "tf_weapon_wrench", "tf_weapon_bonesaw", "tf2c_weapon_umbrella",
              "tf2c_weapon_scythe", "tf2c_weapon_anchor", "tf2c_weapon_chains", "tf2c_weapon_taser"},
}
CLIPLESS = {"tf2c_weapon_doubleshotgun", "tf_weapon_minigun", "tf_weapon_flamethrower", "tf_weapon_sniperrifle",
            "tf_weapon_compound_bow"}

# (attribute class, positive name, negative name, lo, hi, kind) ; kind: mult | add | flag
# Ranges are the CONFIGURABLE defaults ("uncapped" = widen them in config); the safety caps
# below are enforced regardless (see SAFETY).
COMMON = [("mult_dmg", "damage bonus", "damage penalty", 0.25, 3.0, "mult"),
          ("mult_deploy_time", "deploy time decreased", "deploy time increased", 0.3, 3.0, "mult_inv"),
          ("add_maxhealth", "max health additive bonus", "max health additive penalty", -60, 100, "add"),
          ("add_health_regen", "health regen", "health drain", -6, 8, "add"),
          ("mult_player_movespeed", "move speed bonus", "move speed penalty", 0.6, 1.4, "mult"),
          ("set_dmgtype_ignite", "Set DamageType Ignite", None, 1, 1, "flag"),
          ("mult_crit_chance", None, "crit mod disabled", 0, 0, "flag_neg"),
          ("add_onhit_addhealth", "heal on hit for slowfire", "selfdmg on hit for slowfire", -10, 15, "add"),
          ("apply_z_velocity_on_damage", "apply z velocity on damage", None, 150, 600, "add"),
          ("customslop_ignite_self", "customslop ignite self on attack", None, 2, 6, "add")]
GUN = [("mult_postfiredelay", "fire rate bonus", "fire rate penalty", 0.35, 3.0, "mult_inv"),
       ("mult_clipsize", "clip size bonus", "clip size penalty", 0.25, 4.0, "mult"),
       ("mod_max_primary_clip_override", "mod max primary clip override", None, 1, 30, "int"),
       ("mult_reload_time", "Reload time decreased", "Reload time increased", 0.4, 6.0, "mult_inv"),
       ("mult_maxammo", "maxammo {ammo} increased", "maxammo {ammo} reduced", 0.05, 3.0, "mult")]
HITSCAN = [("mult_spread_scale", "weapon spread bonus", "spread penalty", 0.2, 4.0, "mult_inv"),
           ("mult_bullets_per_shot", "bullets per shot bonus", None, 1.5, 4.0, "mult")]
PROJ = [("mult_projectile_speed", "Projectile speed increased", "Projectile speed decreased", 0.4, 2.5, "mult"),
        ("custom_projectile_model", "custom projectile model", None, None, None, "model")]
EXPLOSIVE = [("mult_explosion_radius", "Blast radius increased", "Blast radius decreased", 0.4, 2.0, "mult")]
MELEE = [("mult_postfiredelay", "fire rate bonus", "fire rate penalty", 0.4, 2.5, "mult_inv"),
         ("melee_range_multiplier", "melee range multiplier", None, 0.6, 3.0, "mult"),
         ("hit_self_on_miss", "hit self on miss", None, 1, 1, "flag")]
SAFETY = {"min_fire_interval_projectile_mult": 0.5,   # projectile weapons never fire >2x their stock rate
          "max_pellets_mult": 4.0, "min_movespeed": 0.5, "max_movespeed": 1.6, "max_melee_range": 3.0,
          "min_projectile_speed": 0.35, "max_blast": 2.0, "max_health_floor": -80}

CUSTOM_ATTRS = {CS_ATTR_FIRST: dict(name="customslop ignite self on attack", attribute_class="customslop_ignite_self",
                                    description_string="Sets the wielder on fire for %s1 seconds on every attack",
                                    description_format="value_is_additive", effect_type="negative",
                                    stored_as_integer="0")}


def load_schema(p):
    root = kv.load(p)[0]
    return root.get("items_game") or root


def donors(include_merc=False):
    out = []
    base = load_schema(BASE_SCHEMA).get("items")
    prefabs = load_schema(BASE_SCHEMA).get("prefabs")
    for k, it in base.blocks():
        if not k.isdigit():
            continue
        ic = it.get("item_class") or ""
        fam = next((f for f, s in FAMILY.items() if ic in s), None)
        ubc = it.get("used_by_classes")
        if not fam or not isinstance(ubc, kv.KV) or not it.get("model_player"):
            continue
        out.append(dict(src="tf2c", id=int(k), kv=it, fam=fam, classes=[c.capitalize() for c, _ in ubc.pairs],
                        slot=it.get("item_slot")))
    af = load_schema(AF_SCHEMA).get("items")
    for k, it in af.blocks():
        ic = it.get("item_class") or ""
        fam = next((f for f, s in FAMILY.items() if ic in s), None)
        ubc = it.get("used_by_classes")
        if fam and it.get("model_player") and isinstance(ubc, kv.KV):
            out.append(dict(src="aprilfools", id=int(k), kv=it, fam=fam, classes=[c.capitalize() for c, _ in ubc.pairs],
                            slot=it.get("item_slot")))
    if include_merc and os.path.exists(TF2CC_SCHEMA):
        tc = load_schema(TF2CC_SCHEMA).get("items")
        for k, it in tc.blocks():
            if not k.startswith("301") or int(k) > 30119 or int(k) in (30104, 30119):  # no plugin-driven specials
                continue
            ic = it.get("item_class") or ""
            fam = next((f for f, s in FAMILY.items() if ic in s), None)
            if fam:
                out.append(dict(src="of_merc", id=int(k), kv=it, fam=fam, classes=["Soldier"], slot=it.get("item_slot")))
    return out


def roll_attr(rng, spec, ctx):
    cls, pos, neg, lo, hi, kind = spec
    if kind == "flag":
        return cls, pos, 1
    if kind == "flag_neg":
        return cls, neg, 0
    if kind == "model":
        return cls, pos, rng.choice(ctx["proj_models"])
    if kind == "int":
        return cls, pos, rng.randint(int(lo), int(hi))
    if kind == "add":
        v = round(rng.uniform(lo, hi))
        if v == 0:
            v = 1
        return cls, (pos if v > 0 else neg) or pos, v      # additive values keep their sign
    # log-uniform multipliers, so x0.5 and x2 are equally likely
    import math
    v = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    v = round(v, 2)
    better = v > 1 if kind == "mult" else v < 1
    nm = pos if better or not neg else neg
    if "{ammo}" in (nm or ""):
        nm = nm.format(ammo=ctx["ammo"])
        cls = "mult_maxammo_" + ctx["ammo"]
    return cls, nm, v


def apply_safety(attrs, fam):
    a = {c: v for c, (_, v) in attrs.items()}
    if fam in ("rocket", "grenade", "projectile") and "mult_postfiredelay" in a:
        attrs["mult_postfiredelay"] = (attrs["mult_postfiredelay"][0], max(a["mult_postfiredelay"], SAFETY["min_fire_interval_projectile_mult"]))
    if "mult_bullets_per_shot" in a:
        attrs["mult_bullets_per_shot"] = (attrs["mult_bullets_per_shot"][0], min(a["mult_bullets_per_shot"], SAFETY["max_pellets_mult"]))
    if "mult_player_movespeed" in a:
        v = min(max(a["mult_player_movespeed"], SAFETY["min_movespeed"]), SAFETY["max_movespeed"])
        attrs["mult_player_movespeed"] = ("move speed bonus" if v >= 1 else "move speed penalty", v)
    if "mult_projectile_speed" in a:
        attrs["mult_projectile_speed"] = (attrs["mult_projectile_speed"][0], max(a["mult_projectile_speed"], SAFETY["min_projectile_speed"]))
    if "mult_explosion_radius" in a:
        attrs["mult_explosion_radius"] = (attrs["mult_explosion_radius"][0], min(a["mult_explosion_radius"], SAFETY["max_blast"]))
    if "melee_range_multiplier" in a:
        attrs["melee_range_multiplier"] = (attrs["melee_range_multiplier"][0], min(a["melee_range_multiplier"], SAFETY["max_melee_range"]))
    # a clip override and a clip multiplier together are confusing: keep the override
    if "mod_max_primary_clip_override" in a and "mult_clipsize" in a:
        del attrs["mult_clipsize"]
    return attrs


def traits_of(attrs, fam, wrong):
    t = []
    a = {c: v for c, (_, v) in attrs.items()}
    if "customslop_ignite_self" in a: t.append("self_ignite")
    if "set_dmgtype_ignite" in a: t.append("ignite")
    if a.get("mod_max_primary_clip_override", 99) <= 2 or a.get("mult_clipsize", 1) <= 0.3: t.append("tiny_clip")
    if a.get("mult_reload_time", 1) >= 2.5: t.append("slow_reload")
    if a.get("mult_postfiredelay", 1) <= 0.5: t.append("fast")
    if a.get("mult_postfiredelay", 1) >= 2: t.append("slow")
    if a.get("mult_dmg", 1) >= 2: t.append("big_damage")
    if a.get("mult_dmg", 1) <= 0.4: t.append("weak")
    if min(a.get("mult_maxammo_primary", 1), a.get("mult_maxammo_secondary", 1)) <= 0.15: t.append("low_reserve")
    if "custom_projectile_model" in a: t.append("odd_projectile")
    if wrong: t.append("wrong_class")
    return t


def make_weapon(rng, defindex, donor, ctx, used_names, ill_fit, multi):
    d = donor["kv"]
    fam = donor["fam"]
    slot = donor["slot"]
    home = [c for c in donor["classes"] if c in CLASSES] or ["Soldier"]
    classes = {rng.choice(home): "1"}
    wrong = None
    if rng.random() < ill_fit:
        cand = [c for c in CLASSES if c not in home]
        c = rng.choice(cand)
        s = slot if slot in CLASS_SLOTS[c] else ("melee" if fam == "melee" else
                                                  next((x for x in ("primary", "secondary") if x in CLASS_SLOTS[c]), None))
        if s:
            classes = {c: ("1" if s == slot else s)}
            wrong = c
    if rng.random() < multi:
        c2 = rng.choice([c for c in CLASSES if c not in classes])
        s2 = slot if slot in CLASS_SLOTS[c2] else None
        if s2:
            classes[c2] = "1"
    pool = list(COMMON)
    if fam != "melee" and fam != "flame":
        pool += [g for g in GUN if not (donor["kv"].get("item_class") in CLIPLESS and g[0] in ("mult_clipsize", "mod_max_primary_clip_override"))]
    if fam == "hitscan":
        pool += HITSCAN
    if fam in ("rocket", "grenade"):
        pool += PROJ + EXPLOSIVE
    if fam == "projectile":
        pool += PROJ[:1]
    if fam == "melee":
        pool += MELEE
    ctx = dict(ctx, ammo="primary" if slot == "primary" else "secondary")
    n_attr = rng.randint(3, 7)
    attrs = {}
    for spec in rng.sample(pool, min(n_attr, len(pool))):
        c, nm, v = roll_attr(rng, spec, ctx)
        if nm:
            attrs[c] = (nm, v)
    attrs = apply_safety(attrs, fam)
    name = names.make_name(rng, used_names)
    tr = traits_of(attrs, fam, wrong)
    proj = attrs.get("custom_projectile_model", (None, ""))[1].split("/")[-1].replace(".mdl", "").replace("_", " ")
    desc = names.make_description(rng, tr, dict(proj=proj or "something", cls=wrong or "anyone"))
    tint = dict(hue_deg=rng.choice([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]),
                sat=round(rng.uniform(0.6, 1.6), 2), section_tint=[round(rng.random(), 2) for _ in range(3)])
    mesh = dict(stretch=round(rng.choice([rng.uniform(0.6, 0.9), rng.uniform(1.1, 1.9)]), 2),
                pivot=round(rng.uniform(0.3, 0.6), 2), bulge=round(rng.uniform(-0.3, 0.6), 2),
                bulge_at=round(rng.uniform(0.5, 0.95), 2), bulge_width=round(rng.uniform(0.05, 0.15), 2),
                bend=round(rng.choice([0, 0, rng.uniform(-20, 20)]), 1))
    return dict(defindex=defindex, name=name, description=desc, donor=dict(src=donor["src"], id=donor["id"],
                item_class=d.get("item_class")), family=fam, slot=slot, classes=classes, wrong_class=wrong,
                attributes={c: dict(name=nm, value=v) for c, (nm, v) in attrs.items()}, traits=tr,
                recolor=tint, mesh=mesh)


def emit_item(w, donor_kv, asset_tier):
    d = donor_kv
    it = kv.KV()
    it.add("name", "customslop_%d" % w["defindex"])
    it.add("item_name", w["name"])
    it.add("item_type_name", d.get("item_type_name") or "#TF_Weapon")
    it.add("item_description", w["description"])
    it.add("item_quality", "normal")
    it.add("propername", "1")
    it.add("item_class", d.get("item_class"))
    it.add("item_slot", w["slot"])
    ubc = kv.KV()
    for c, s in w["classes"].items():
        ubc.add(c, s)
    it.add("used_by_classes", ubc)
    for key in ("anim_slot", "attach_to_hands", "flip_viewmodel", "bucket", "item_logname", "item_iconname",
                "mouse_pressed_sound", "drop_sound", "extra_wearable"):
        if d.get(key) is not None:
            it.add(key, d.get(key))
    if asset_tier >= 2:
        it.add("model_player", "models/customslop/cs%d/v_cs%d.mdl" % (w["defindex"], w["defindex"]))
        it.add("model_world", "models/customslop/cs%d/w_cs%d.mdl" % (w["defindex"], w["defindex"]))
        it.add("image_inventory", "backpack/customslop/cs%d" % w["defindex"])
    else:
        for key in ("model_player", "model_world", "image_inventory", "image_inventory_size_w", "image_inventory_size_h"):
            if d.get(key) is not None:
                it.add(key, d.get(key))
    for key in ("static_attrs", "visuals", "visuals_red", "visuals_blu", "visuals_grn", "visuals_ylw"):
        if isinstance(d.get(key), kv.KV):
            it.add(key, d.get(key))
    attrs = kv.KV()
    keep = d.get("attributes")
    if isinstance(keep, kv.KV):          # functional donor attributes (not the donor's own stat tweaks)
        for an, av in keep.blocks():
            c = av.get("attribute_class")
            if c in ("custom_projectile_model", "mod_sticky_is_landmine", "mod_sticky_is_proxy", "mod_sticky_fizzles",
                     "stickybomb_charge_rate", "chargeweapon_no_extra_speed", "auto_fires_full_clip", "set_weapon_range",
                     "mod_burstfire", "mod_shoot_self") and c not in w["attributes"]:
                attrs.add(an, av)
    for c, a in w["attributes"].items():
        b = kv.KV()
        b.add("attribute_class", c)
        b.add("value", str(a["value"]))
        attrs.add(a["name"], b)
    it.add("attributes", attrs)
    tags = kv.KV()
    tags.add("customslop", "1")
    it.add("tags", tags)
    return it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--cap", type=int, default=50)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--ill-fit", type=float, default=0.15)
    ap.add_argument("--multi", type=float, default=0.10)
    ap.add_argument("--asset-tier", type=int, default=1, help="1: stock models+icons (MVP); 2: mutated models + rendered icons")
    ap.add_argument("--merge-from", default=TF2CC_SCHEMA if os.path.exists(TF2CC_SCHEMA) else AF_SCHEMA)
    ap.add_argument("--include-merc", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "gen"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sp = os.path.join(a.out, "state.json")
    state = json.load(open(sp)) if os.path.exists(sp) else {"next_defindex": DEFINDEX_FIRST, "weapons": [], "retired": []}
    if any(w["date"] == a.date for w in state["weapons"]):
        print("already generated for", a.date)
        return
    seed = a.seed if a.seed is not None else int(a.date.replace("-", ""))
    rng = random.Random(seed)
    used = {w["name"].lower() for w in state["weapons"] + state["retired"]}
    pool = donors(a.include_merc)
    roster = json.load(open(os.path.join(ROOT, "analysis", "projectile_model_candidates.json")))
    roster = [m for m in roster if "skybox" not in m and "/effects/" not in m]
    ctx = dict(proj_models=roster)
    new = []
    for _ in range(a.count):
        di = state["next_defindex"]
        assert di <= DEFINDEX_LAST, "defindex range exhausted"
        state["next_defindex"] = di + 1
        donor = rng.choice(pool)
        w = make_weapon(rng, di, donor, ctx, used, a.ill_fit, a.multi)
        w["date"] = a.date
        w["asset_tier"] = a.asset_tier
        new.append(w)
    state["weapons"] += new
    # rotation at the cap: oldest out (schema + repo assets); defindexes are never reused
    while len(state["weapons"]) > a.cap:
        state["retired"].append(state["weapons"].pop(0))
    json.dump(state, open(sp, "w"), indent=1)
    # ---- emit schema block
    dmap = {(d["src"], d["id"]): d["kv"] for d in donors(True)}
    items = kv.KV()
    for w in state["weapons"]:
        items.add(str(w["defindex"]), emit_item(w, dmap[(w["donor"]["src"], w["donor"]["id"])], w.get("asset_tier", 1)))
    attrs = kv.KV()
    for k, v in CUSTOM_ATTRS.items():
        b = kv.KV()
        for kk, vv in v.items():
            b.add(kk, vv)
        attrs.add(str(k), b)
    block = "// CustomSlop: generated %s, %d weapons (do not edit)\n" % (a.date, len(state["weapons"]))
    block += '"items"\n{\n' + kv.dump(items, 1) + '}\n"attributes"\n{\n' + kv.dump(attrs, 1) + "}\n"
    open(os.path.join(a.out, "customslop_items.txt"), "w", encoding="utf-8").write(block)
    # ---- merge: append our items/attributes into the existing items_game root
    base = kv.load(a.merge_from)[0]
    ig = base.get("items_game")
    for key, blk in (("items", items), ("attributes", attrs)):
        tgt = ig.get(key)
        if tgt is None:
            tgt = kv.KV()
            ig.add(key, tgt)
        tgt.pairs = [(k, v) for k, v in tgt.pairs if not (k.isdigit() and DEFINDEX_FIRST - 100 <= int(k) <= DEFINDEX_LAST)]
        tgt.pairs += blk.pairs
    merged = '#base "items_game.txt"\n' + kv.dump(base)
    mp = os.path.join(a.out, "custom_items_game.txt")
    open(mp, "w", encoding="utf-8").write(merged)
    # ---- today.json for plugin/webhook
    today = [dict(defindex=w["defindex"], name=w["name"], classes=list(w["classes"]),
                  slot=w["slot"], description=w["description"]) for w in new]
    json.dump(dict(date=a.date, weapons=today, total=len(state["weapons"]),
                   ad="Today's %d new weapons: %s" % (len(today), ", ".join("%s (%s)" % (t["name"], "/".join(t["classes"])) for t in today))),
              open(os.path.join(a.out, "today.json"), "w"), indent=1)
    # ---- validation
    rep = validate(mp, state)
    json.dump(rep, open(os.path.join(a.out, "customslop_schema_report.json"), "w"), indent=1)
    print(json.dumps(dict(new=[(w["defindex"], w["name"], w["classes"], w["donor"]) for w in new], report=rep), indent=1))


def validate(path, state):
    base = load_schema(BASE_SCHEMA)
    known = {a.get("name").lower() for _, a in base.get("attributes").blocks()}
    m = load_schema(path)
    known |= {a.get("name").lower() for _, a in m.get("attributes").blocks() if a.get("name")}
    rep = dict(file_bytes=os.path.getsize(path), errors=[], items=0)
    ids = [k for k, _ in m.get("items").blocks() if k.isdigit()]
    rep["duplicate_defindex"] = len(ids) != len(set(ids))
    names_seen = set()
    for k, it in m.get("items").blocks():
        if not (k.isdigit() and DEFINDEX_FIRST <= int(k) <= DEFINDEX_LAST):
            continue
        rep["items"] += 1
        nm = it.get("name")
        if nm in names_seen:
            rep["errors"].append("%s duplicate name %s" % (k, nm))
        names_seen.add(nm)
        for an, av in it.get("attributes").blocks():
            if an.lower() not in known:
                rep["errors"].append("%s unknown attribute name %r" % (k, an))
        for c, s in it.get("used_by_classes").pairs:
            sl = it.get("item_slot") if s == "1" else s
            if sl not in CLASS_SLOTS[c]:
                rep["errors"].append("%s slot %s invalid for %s" % (k, sl, c))
        for key in ("item_name", "item_description"):
            if len(it.get(key) or "") > 200:
                rep["errors"].append("%s %s too long" % (k, key))
    import bz2
    rep["bz2_bytes"] = len(bz2.compress(open(path, "rb").read()))
    return rep


if __name__ == "__main__":
    main()
