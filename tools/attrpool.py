"""CustomSlop attribute pool v2: EVERY attribute in the TF2C 5205 item schema is considered.

Each schema attribute definition gets exactly one disposition:
  allowed  - may be rolled freely (weight by usefulness on a base family)
  guarded  - may be rolled, but its value is clamped / restricted to a whitelist (crash/edict/
             physics safety) - see GUARDS
  excluded - never rolled, with a reason (econ metadata, needs an asset/ID we can't validate,
             would crash, or is a schema-internal marker)
Usefulness per weapon family comes from read sites (CALL_ATTRIB_HOOK sites in the 2024 source,
presence of the class string in the 5205 server.dll): an attribute with no read site anywhere,
or read only by another weapon family's code, is still allowed but weighted low.
Value direction: percentage/inverted pairs decide which side of 1.0 each definition's value
lies on, so the rendered TF2 description reads correctly ("+25% damage bonus").

Writes analysis/attribute_pool_5205.json and prints the counts.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import loc as LOC  # noqa: E402
import cspaths as P  # noqa: E402

CAT = os.path.join(ROOT, "analysis", "attributes_5205.json")
MVM = P.data("mvm_upgrades.txt")
OUT = os.path.join(ROOT, "analysis", "attribute_pool_5205.json")

# file-name stems -> weapon families that read the attribute there
FAMILY_FILES = {
    "hitscan": ("tf_weapon_shotgun", "tf_weapon_pistol", "tf_weapon_smg", "tf_weapon_revolver", "tf_weapon_sniperrifle",
                "tf_weapon_minigun", "tf_weapon_scattergun", "tf_weaponbase_gun", "tf_fx_shared", "tf2c_weapon_hunting_revolver",
                "tf_weapon_doubleshotgun", "tf_weapon_aagun"),
    "rocket": ("tf_weapon_rocketlauncher", "tf_weaponbase_rocket", "tf_projectile_rocket", "tf_weaponbase_gun"),
    "grenade": ("tf_weapon_grenadelauncher", "tf_weapon_pipebomblauncher", "tf_weaponbase_grenadeproj", "tf_weapon_grenade_pipebomb",
                "tf_weaponbase_gun", "tf_projectile_cyclopsgrenade"),
    "projectile": ("tf_weapon_nailgun", "tf_projectile_nail", "tf_weapon_flaregun", "tf_projectile_flare", "tf_weapon_compound_bow",
                   "tf_projectile_arrow", "tf_weaponbase_gun", "tf_projectile_coil", "tf_projectile_dart", "tf_weapon_syringegun"),
    "flame": ("tf_weapon_flamethrower",),
    "melee": ("tf_weaponbase_melee", "tf_weapon_knife", "tf_weapon_bat", "tf_weapon_wrench", "tf_weapon_bottle", "tf_weapon_fists",
              "tf_weapon_shovel", "tf_weapon_bonesaw", "tf_weapon_fireaxe", "tf_weapon_club", "tf_weapon_sword"),
}
GENERIC_FILES = ("tf_player", "tf_player_shared", "tf_weaponbase", "tf_gamerules", "tf_obj", "tf_condition", "tf_baseprojectile",
                 "attribute_manager", "tf_wearable", "econ", "tf_item", "baseobject")

EXCLUDE = [  # (regex on class or name, reason)
    (r"^(kill_eater|strange|killstreak|paint|set_item_tint|item_style|attach_particle|unusual|custom_name|custom_desc|gifter|"
     r"event_date|elevate_quality|is_|cannot_|tradable|limited_|always_tradable|collection|series|crate|supply_crate|"
     r"dynamic_recipe|tool_|recipe|decoded|unlimited_quantity|purchased|preserve|halloween_spell|spell_|loot_rarity|"
     r"wide_item_level|deactive_date|taunt_|cosmetic|quest|saxxy|style_|minimum_level|is_australium|item_slot_criteria|"
     r"makers_mark|referenced_item|zombie|footstep|operation|duck|ducks|mvm_completed|gift|weapon_allow_inspect|inspect)",
     "econ/cosmetic metadata (no gameplay effect, or needs item-server data)"),
    (r"(_explain|explain$|separator|desc_)", "description-only marker (text, no effect)"),
    (r"^(set_weapon_mode|mod_weapon_mode|weapon_mode)", "indexes weapon-mode arrays; out-of-range values crash"),
    (r"^(add_cond|addcond|lunchbox_addcond|mod_set_banner_cond|set_banner_cond|spawn_with_physics_toy|"
     r"mod_ubercharge_cond|add_cond_on_active|cond_on_active)", "takes a condition ID; random IDs can crash (use the guarded whitelist pickers instead)"),
    (r"^(custom_hand_viewmodel|custom_magazine_model|custom_lunchbox_throwable_model|custom_item_model|model_|"
     r"custom_projectile_particle|projectile_particle_name|custom_banner_sound|override_footstep|custom_impact_sound|"
     r"particle_effect|tracer|class_select_override_vcd|explosion_particle|custom_sound|sound_)",
     "string attribute that needs a valid asset path (only picked from validated lists)"),
    (r"^(mod_burstfire)$", "string syntax unverified on 5205 (tf2cc uses '3 0.2333' only)"),
    (r"^(experimental_weapon|allowed_in_medieval_mode|item_level|item_quality|set_supply_crate|bots_cant_use|"
     r"preview_|hidden_|min_viewmodel_offset|inspect_viewmodel_offset)", "schema/meta flag, not a weapon effect"),
    (r"^(apply_z_velocity_on_damage_only|sapper_|robo_sapper|recall|canteen|bidirectional_teleport|building_instant_upgrade|"
     r"engy_disposable)", "needs a building/canteen system that a random weapon slot does not drive"),
]

# guarded: (regex on class, kind, params) - value clamps/whitelists that keep the server alive.
# Standing rule (user 2026-11-20): these are ENGINE/CRASH safety bounds only, never balance caps;
# ridiculous values in either direction are intended (widened 2026-11-20, engine-tested: extremetest.py).
GUARDS = [
    (r"^override_projectile_type(_zoomed)?$", "whitelist", "per-base whitelist of 5205 projectile IDs the base gun fires (bullet 1, rocket 2, pipe 3, sticky 4, syringe 5, flare 6, arrow 8, cannonball 17, nail 31, brick 32, coil 33, mirv 34, dart 39); untested combos stay off until the test-server matrix passes"),
    (r"^custom_projectile_model$", "list", "only models from analysis/projectile_model_candidates.json (4-40 u, TF2/TF2C content the client already has); rocket/grenade bases only"),
    (r"^mod_projectiles_per_shot$", "clamp", [1, 3]),
    (r"^mult_bullets_per_shot$", "clamp", [0.5, 6.0]),
    (r"^mult_postfiredelay$", "clamp", [0.08, 10.0]),
    (r"^mult_player_movespeed|movespeed", "clamp", [0.2, 3.0]),
    (r"^mod_set_player_scale|player_scale|model_scale", "clamp", [0.5, 1.5]),
    (r"^(head_scale|torso_scale|hand_scale|voice_pitch)", "clamp", [0.4, 2.5]),
    (r"^add_maxhealth", "clamp", [-100, 300]),
    (r"^(mult_clipsize|mult_clipsize_upgrade)$", "clamp", [0.05, 20.0]),
    (r"^mod_max_primary_clip_override$", "clamp", [1, 200]),
    (r"^mult_maxammo", "clamp", [0.05, 10.0]),
    (r"^mult_explosion_radius$", "clamp", [0.1, 5.0]),
    (r"^mult_projectile_scale$", "clamp", [0.3, 3.0]),
    (r"^mult_projectile_speed$", "clamp", [0.1, 5.0]),
    (r"^(apply_z_velocity_on_damage|apply_look_velocity_on_damage)$", "clamp", [-600, 900]),
    (r"^(mult_dmgself_push_force|damage_force|airblast_pushback_scale|mult_.*knockback)", "clamp", [0.0, 10.0]),
    (r"^(mult_dmg|mult_dmg_.*)$", "clamp", [0.02, 20.0]),
    (r"^(mult_reload_time|mult_deploy_time|mult_switch_from_wep_deploy_time|mult_.*_time)$", "clamp", [0.05, 10.0]),
    (r"^(add_health_regen|active_item_health_regen)$", "clamp", [-15, 25]),
    (r"^mod_jump_height|jump_height", "clamp", [0.2, 4.0]),
    (r"^(mult_gravity|gravity)", "clamp", [0.1, 5.0]),
    (r"^melee_range_multiplier$", "clamp", [0.3, 6.0]),
    (r"^set_weapon_range$", "clamp", [64, 4096]),
]

CUSTOM = [  # CustomSlop's own VScript attributes (defined in the CustomSlop schema block)
    dict(id=25900, name="customslop ignite self on attack", cls="customslop_ignite_self", effect="negative",
         fmt="value_is_additive", desc="Sets the wielder on fire for %s1 seconds on every attack", vscript=True),
]


SET_BONUS = None
KVDIR = os.path.dirname(os.path.abspath(__file__))
BASE_SCHEMA = P.data("items_game.txt")


def set_bonus_names():
    """Attribute names flagged is_set_bonus in the TF2C schema. Build 5205 REJECTS the whole custom
    schema ("Item schema load failed") if an item uses one - found by the engine-load test."""
    global SET_BONUS
    if SET_BONUS is None:
        sys.path.insert(0, KVDIR)
        import kv as _kv
        ig = _kv.load(BASE_SCHEMA)[0].get("items_game")
        SET_BONUS = {a.get("name").lower() for _, a in ig.get("attributes").blocks()
                     if a.get("name") and (a.get("is_set_bonus") == "1" or a.get("name").lower().startswith("set bonus:"))}
    return SET_BONUS


def disposition(a):
    cls, name = (a["cls"] or ""), (a["name"] or "")
    if not cls:
        return "excluded", "no attribute_class"
    if name.lower() in set_bonus_names():
        return "excluded", "set bonus attribute: build 5205 rejects the WHOLE custom schema if an item uses one"
    if a.get("type") and a["type"] not in ("string",) and a["type"] != "float":
        return "excluded", "non-numeric econ attribute type (%s)" % a["type"]
    if a["fmt"] in ("value_is_date", "value_is_account_id", "value_is_item_def", "value_is_particle_index",
                    "value_is_killstreakeffect_index", "value_is_killstreak_idleeffect_index", "value_is_from_lookup_table"):
        return "excluded", "econ value format %s" % a["fmt"]
    for rx, why in EXCLUDE:
        if re.search(rx, cls) or re.search(rx, name.lower().replace(" ", "_")):
            return "excluded", why
    if a.get("type") == "string":
        for rx, kind, p in GUARDS:
            if re.search(rx, cls):
                return "guarded", p if isinstance(p, str) else "%s %s" % (kind, p)
        return "excluded", "string attribute without a validated value list"
    for rx, kind, p in GUARDS:
        if re.search(rx, cls):
            return "guarded", p if isinstance(p, str) else "%s %s" % (kind, p)
    return "allowed", ""


def usefulness(a):
    stems = {re.sub(r"\.(cpp|h)$", "", f) for f in a.get("files", [])}
    fam = {}
    generic = any(s.startswith(GENERIC_FILES) for s in stems)
    for f, files in FAMILY_FILES.items():
        fam[f] = 1.0 if generic or any(s.startswith(files) for s in stems) else (0.25 if (stems or a.get("in_5205_server")) else 0.1)
    return fam


MAGNITUDE_WORDS = re.compile(r"(?:^|\W)(slower|faster|longer|shorter|more|less|fewer|increased?|decreased?|reduced|larger|"
                             r"smaller|bigger|higher|lower|extra|additional|up to|seconds?|by|delays?|duration)(?:\W|$)", re.I)


def direction(a, by_class, L):
    """Desired sign of the DISPLAYED number (TF2 formatting), from the localised string:
    'flag'  no %s1 in the text (on/off attribute) or value_is_or
    'pos'   +%s1 / -%s1 (the string carries the sign) or a magnitude wording ('% slower', 'seconds')
    'neg'   plain %s1 on a negative-effect line ('%s1% damage penalty', '%s1 max health on wearer')"""
    fmt, eff = a["fmt"], a["effect"]
    s = (L.get(a["desc"] or "", "") or "") if a.get("desc") else ""
    if fmt == "value_is_or" or (s and "%s1" not in s):
        return "flag"
    st = s.strip()
    if st.startswith(("+%s1", "-%s1")) or MAGNITUDE_WORDS.search(s):
        return "pos"
    if not s:
        return "pos" if eff != "negative" else "neg"
    return "neg" if eff == "negative" else "pos"


def build():
    rows = json.load(open(CAT))
    L = LOC.Loc()
    mvm = set()
    if os.path.exists(MVM):
        mvm = {m.lower() for m in re.findall(r'"attribute"\s+"([^"]+)"', open(MVM, encoding="latin-1").read())}
    by_class = {}
    for r in rows:
        by_class.setdefault(r["cls"], []).append(r)
    pool = []
    for r in rows:
        d, why = disposition(r)
        desc = L.get(r["desc"]) if r["desc"] else None
        pool.append(dict(id=r["id"], name=r["name"], cls=r["cls"], fmt=r["fmt"], effect=r["effect"], hidden=r["hidden"],
                         desc_token=r["desc"], desc_text=desc if desc and not desc.startswith("#") else None,
                         disposition=d, reason=why, mvm=(r["name"] or "").lower() in mvm,
                         read_2024=r["hooked_2024"], in_5205=r["in_5205_server"],
                         weight=usefulness(r), direction=direction(r, by_class, L), integer=r["integer"]))
    for c in CUSTOM:
        pool.append(dict(id=c["id"], name=c["name"], cls=c["cls"], fmt=c["fmt"], effect=c["effect"], hidden=False,
                         desc_token=None, desc_text=c["desc"], disposition="allowed", reason="CustomSlop VScript", mvm=False,
                         read_2024=False, in_5205=False, weight={f: 1.0 for f in FAMILY_FILES}, direction="pos", integer=False,
                         vscript=True))
    json.dump(pool, open(OUT, "w"), indent=1)
    import collections
    c = collections.Counter(p["disposition"] for p in pool)
    reasons = collections.Counter(p["reason"] for p in pool if p["disposition"] == "excluded")
    noread = sum(1 for p in pool if p["disposition"] != "excluded" and not p["read_2024"] and not p["in_5205"])
    summary = dict(total=len(pool), schema_defs=len(rows), custom=len(CUSTOM), allowed=c["allowed"], guarded=c["guarded"],
                   excluded=c["excluded"], excluded_reasons=reasons.most_common(),
                   mvm_upgrade_attrs=sum(p["mvm"] for p in pool),
                   mvm_rollable=sum(1 for p in pool if p["mvm"] and p["disposition"] != "excluded"),
                   rollable_without_read_site=noread,
                   rollable_hidden=sum(1 for p in pool if p["disposition"] != "excluded" and p["hidden"]),
                   rollable_with_tf2_description=sum(1 for p in pool if p["disposition"] != "excluded" and p["desc_text"]))
    json.dump(summary, open(os.path.join(ROOT, "analysis", "attribute_pool_summary.json"), "w"), indent=1)
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
