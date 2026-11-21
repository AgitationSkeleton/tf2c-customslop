"""Reviewed effect table: which attribute DEFINITIONS CustomSlop may roll, and with which values,
so that every rolled stat does something a player can see and reads true (user bug 2026-11-20:
"favoring negative health on hit attributes which don't actually work ... make sure every
attribute applied to a customslop weapon actually works and does something, with the exception of
one or two deliberately-joke stats").

Reviewed against the TF2C 2024 game source read sites (analysis/attr_sign_dump_5205.txt lists every rollable
definition with the code after each CALL_ATTRIB_HOOK site) and the 5205 engine (onhittest.py,
attrtest.py). WHITELIST: a pool definition that is not listed here is never rolled.

Entry fields
  v      (lo, hi) the WHOLE working range, rolled uniformly (ints -> integer roll); a flag is (1, 1).
         Standing rule (user 2026-11-20): ridiculous values in either direction are intended; a
         range is limited only by engine/crash safety, by the text staying true (sign/side) and by
         the value still doing something (e.g. heals cap at max health/overheal, 3 stored crits
         max, clip <= 254 = 8-bit network field). None = the generic roller (pipeline.roll_value:
         uniform over the class's safety range on the side the text/mechanics require).
  req    regex the weapon's item_class must match for the stat to do anything (on top of the
         attrscope source gate and relevance tags), e.g. bullets-per-shot only on pellet weapons
  base   the stat changes an integer weapon property (clip): the rolled value must change the
         rounded result for this weapon (see observable())
Hidden attributes and attributes with no description are never rolled (nobody can see them).
Deliberate jokes are not listed here: pipeline.roll_attributes picks them from definitions that
are VISIBLE but provably inert on this weapon (weapon-scoped, not read for this item class / not
relevant), at most JOKE_MAX per weapon, and marks them joke=True.
"""
import re

JOKE_MAX = 2

PELLETS = r"shotgun|scattergun|minigun"
STICKY = r"pipebomblauncher"
GRENADE = r"grenadelauncher|pipebomblauncher|cyclops|mirv"
FLAME = r"flamethrower"
SNIPER = r"sniperrifle"


def ok(lo=None, hi=None, req=None, base=None, note=""):
    return dict(v=None if lo is None else (lo, hi if hi is not None else lo), req=req, base=base, note=note)


SPEC = {
    # ---- on hit / on kill -------------------------------------------------------------------
    # add_onhit_addhealth: in 5205 a POSITIVE value heals that much on hit, but ANY negative value
    # heals +3 instead of hurting (onhittest.py: -18, -15, -12 all gave +3; the 2024 source would
    # self-damage - the 5205 binary does not). Only the heal side is rolled. It used to be on most
    # weapons: 4 definitions of one class x CORE weight x the "meaningful downside" pick.
    "heal on hit for rapidfire": ok(1, 300, note="small per-pellet/per-bullet heal"),
    "heal on hit for slowfire": ok(1, 300),
    "add ammo on direct hit": ok(1, 200),
    "add cloak on hit": ok(1, 100),
    "add uber charge on hit": ok(0.01, 1.0),
    "critboost on kill": ok(1, 60),
    "view punch on hit": ok(1, 1),
    "bleeding duration": ok(1, 60),
    "heal on kill": ok(1, 450),
    "heal on kill on crit": ok(1, 450),
    "gain stored crits on hit": ok(1, 3),
    "gain stored crits on kill": ok(1, 3),
    "lose stored crits on miss": ok(1, 3, req=r"melee|bat|club|shovel|bottle|bonesaw|fireaxe|knife|wrench|fists|"
                                             r"saxxy|umbrella|scythe|chains|anchor"),
    "instant reload on hit": ok(1, 200),
    "instant reload on direct hit": ok(1, 200),
    "tranq on hit": ok(0.5, 20.0),
    "extinguish restores health": ok(1, 300, req=FLAME),
    "flat heal on afterburn on active": ok(1, 100),
    # ---- crits -----------------------------------------------------------------------------
    "crit mod disabled": ok(0, 0, note="mult_crit_chance: 0 = no random crits (was rolled as 1 = no effect)"),
    "mod crit airborne simple": ok(1, 1),
    "crit_dmg_falloff": ok(1, 1),
    "crit from behind": ok(1, 1),
    "crit on objective": ok(1, 1),
    "crit vs bleeding players": ok(1, 1),
    "crit vs wet players": ok(1, 1),
    "mod crit while airborne": ok(1, 1),
    "crits_become_minicrits": ok(1, 1),
    "minicrits become crits": ok(1, 1),
    "mod mini-crit airborne": ok(1, 1),
    "minicrit on objective": ok(1, 1),
    "minicrit while disguised": ok(1, 1),
    # or_crit_vs_(not_)playercond: bitmask over g_eAttributeConditions (burning = bit 0,
    # disguised = bit 4, stunned = bit 16) - "disguised"/"stunned" were rolled as 1 = burning
    "crit vs burning players": ok(1, 1),
    "crit vs non burning players": ok(1, 1),
    "crit vs disguised players": ok(16, 16),
    "crit vs stunned players": ok(65536, 65536),
    "headshot damage increase": ok(),
    "headshot is minicrit": ok(1, 1),
    "damage penalty on bodyshot": ok(req=SNIPER),
    "sniper full charge damage bonus": ok(req=SNIPER),
    "sniper no charge": ok(1, 1, req=SNIPER),
    "scoped firerate penalty": ok(req=SNIPER),
    "sniper charge per sec": ok(req=SNIPER),
    "SRifle Charge rate increased": ok(req=SNIPER),
    "SRifle Charge rate decreased": ok(req=SNIPER),
    # ---- damage ----------------------------------------------------------------------------
    "damage bonus": ok(),
    "CARD: damage bonus": ok(),
    "damage penalty": ok(),
    "dmg bonus vs buildings": ok(),
    "dmg penalty vs buildings": ok(),
    "damage bonus vs burning": ok(),
    "no damage falloff over distance": ok(1, 1),
    "dmg pierces resists absorbs": ok(1, 1),
    "Set DamageType Ignite": ok(1, 1),
    "self mark for death": ok(1, 1),
    "explosive bullets": ok(1, 1, req=r"shotgun|scattergun|pistol|smg|revolver|minigun|sniperrifle|nailgun"),
    # ---- fire rate / clip / ammo -----------------------------------------------------------
    "fire rate bonus": ok(),
    "fire rate penalty": ok(),
    "melee attack rate bonus": ok(),
    "fire rate bonus with reduced health": ok(0.08, 0.95, note="multiplier at 10% health; 1 (old roll) = no effect"),
    "clip size bonus": ok(1.05, 20.0, base="clip"),
    "clip size penalty": ok(0.05, 0.95, base="clip"),
    "Reload time decreased": ok(),
    "Reload time increased": ok(),
    "faster reload rate": ok(),
    "mod ammo per shot": ok(2, 200, note="ammo per shot override (old roll 5-30 emptied the clip in one shot)"),
    "bullets per shot bonus": ok(1.05, 6.0, req=PELLETS, note="int hook: single-bullet weapons would round back to 1"),
    "spread penalty": ok(),
    "weapon spread bonus": ok(),
    "mod horizontal spread": ok(1, 1, req=r"shotgun|scattergun", note="buckshot weapons only"),
    "projectile penetration": ok(1, 1),
    "projectile penetration heavy": ok(1, 10),
    # ---- projectiles / explosives ----------------------------------------------------------
    "Projectile speed increased": ok(),
    "Projectile speed decreased": ok(),
    "Blast radius increased": ok(),
    "Blast radius decreased": ok(),
    "blast dmg to self increased": ok(),
    "no self blast dmg": ok(1, 1),
    "rocket jump damage reduction weapon": ok(0.01, 0.95, note="positive = LESS self damage (old roll 1.1-1.5 = more)"),
    "self dmg push force increased": ok(),
    "self dmg push force decreased": ok(),
    "rocket gravity": ok(0.05, 4.0, req=r"rocketlauncher"),
    "fuse bonus": ok(req=GRENADE),
    "grenade detonation damage penalty": ok(req=GRENADE),
    "grenade no bounce": ok(1, 1, req=GRENADE),
    "sticky air burst mode": ok(2, 2, req=GRENADE, note="TF_DETMODE_FIZZLEONWORLD; 1 (old roll) is unused"),
    "max pipebombs increased": ok(1, 24, req=STICKY),
    "max pipebombs decreased": ok(-7, -1, req=STICKY, note="base 8; old roll -5..-30 left none"),
    "stickybomb charge rate": ok(req=STICKY),
    "sticky fizzles": ok(1, 1, req=STICKY),
    # ---- flamethrower ----------------------------------------------------------------------
    "airblast disabled": ok(1, 1, req=FLAME),
    "mod flamethrower push": ok(1, 1, req=FLAME),
    "airblast cost increased": ok(1.05, 10.0, req=FLAME),
    "airblast cost decreased": ok(0.05, 0.95, req=FLAME, note="was rolled above 1 (= more expensive)"),
    "flame size bonus": ok(1.05, 5.0, req=FLAME),
    "flame size penalty": ok(0.1, 0.95, req=FLAME, note="was rolled above 1 (= bigger flames)"),
    "flame ammopersec increased": ok(req=FLAME),
    "flame ammopersec decreased": ok(req=FLAME),
    "apply self knockback airblast": ok(50, 3000, req=FLAME, note="impulse in u/s; 1 (old roll) = nothing"),
    # ---- movement / self knockback --------------------------------------------------------
    "apply self knockback": ok(50, 3000, note="impulse in u/s; 1 (old roll) = nothing"),
    "apply self knockback on swing": ok(50, 3000),
    "fishwhacker sweep": ok(1, 1),
    "air dash count": ok(1, 1),
    "increased jump height from weapon": ok(),
    "gravity mod active increased": ok(),
    "mult_player_movespeed_active": ok(),
    "aiming movespeed increased": ok(req=r"minigun|sniperrifle|compound_bow"),
    "scattergun has knockback": ok(1, 1, req=r"scattergun"),
    # ---- survivability while active -------------------------------------------------------
    "mult_dmgtaken_active": ok(),
    "dmg taken from fire reduced on active": ok(),
    "less flinching when active": ok(),
    "more flinching when active": ok(),
    "healing received on active bonus": ok(),
    "healing received on active penalty": ok(),
    "health from packs increased on active": ok(),
    "health from packs decreased on active": ok(),
    "medigun healing received on active bonus": ok(),
    "medigun healing received on active penalty": ok(),
    "dispenser healing received on active bonus": ok(),
    "dispenser healing received on active penalty": ok(),
    "health kits can overheal on active": ok(1, 1),
    "dispenser can overheal on active": ok(1, 1),
    "everything can overheal on active": ok(1, 1),
    "mult_patient_overheal_penalty_active": ok(),
    "no metal from dispensers while active": ok(1, 1),
    "no primary ammo from dispensers while active": ok(1, 1),
    # ---- class mechanics (relevance.py restricts these to the class) ----------------------
    "ubercharge rate bonus": ok(),
    "ubercharge rate penalty": ok(),
    "minigun spinup time increased": ok(req=r"minigun"),
    "minigun spinup time decreased": ok(req=r"minigun"),
    "less flinching when aiming": ok(req=r"minigun|sniperrifle"),
    "more flinching when aiming": ok(req=r"minigun|sniperrifle"),
    "minigun no spin sounds": ok(1, 1, req=r"minigun"),
    "Construction rate increased": ok(),
    "Construction rate decreased": ok(),
    "Repair rate increased": ok(),
    "Repair rate decreased": ok(),
    "single wep deploy time decreased": ok(0.05, 0.95),
    "single wep deploy time increased": ok(1.05, 10.0, note="was rolled below 1 (= faster)"),
    "cyclops detonate other grenades": ok(1, 1, req=r"cyclops"),
}

# reviewed and NOT rolled (kept for the audit report; anything else unlisted is dropped too)
DROPPED = {
    "selfdmg on hit for rapidfire": "5205: negative add_onhit_addhealth heals +3 instead of hurting (onhittest.py)",
    "selfdmg on hit for slowfire": "5205: negative add_onhit_addhealth heals +3 instead of hurting (onhittest.py)",
    "mod crit airborne simple min height": "duplicate of 'mod crit airborne simple' at value 1",
    "modifier crit airborne direct hit only": "modifier of another attribute, no effect alone",
    "self knockback affected by damage boost modifier": "modifier of another attribute, no effect alone",
    "provide on active": "scope modifier, no effect of its own",
    "sticky detonate mode": "value 1 is TF_DETMODE_WHATIS1MEANTTOBE - unused by the source; text is wrong",
    "stickybomb charge rate mine layer": "needs value 0 (charge time 0); rolled 1 = nothing",
    "aiming movespeed decreased": "source only applies values that INCREASE speed (maxfbspeedOnAttribute > maxfbspeed)",
    "sniper aiming movespeed decreased": "source only applies values that INCREASE speed",
    "charge time increased": "coilgun only (no CustomSlop coilgun), seconds roll 5-30",
    "charge time decreased": "coilgun only; the 'decreased' definition rolled positive = increase",
    "lifesteal crit": "description ('charged attacks hit multiple enemies') is not what it does",
    "energy weapon no ammo": "energy-weapon only path",
    "effect bar recharge rate increased": "no CustomSlop item has an effect bar",
}



def spec(defn_name):
    return SPEC.get(defn_name)


def allowed(p, item_class):
    """p = attribute_pool row. Rollable as a NORMAL (working) stat on this item class?"""
    s = SPEC.get(p["name"])
    if not s or p.get("hidden") or not p.get("desc_text"):
        return False
    return not s["req"] or bool(re.search(s["req"], item_class or "", re.I))


def roll(p, rng):
    """Uniform over the definition's whole working range (user 2026-11-20: values are "truly random"
    as long as the item works and does what it says - no shaping, no balance caps), or None (the
    generic roller handles it, also uniform over the class's safety range)."""
    s = SPEC.get(p["name"])
    if not s or not s["v"]:
        return None
    lo, hi = s["v"]
    if isinstance(lo, int) and isinstance(hi, int):
        return rng.randint(min(lo, hi), max(lo, hi))
    return round(rng.uniform(min(lo, hi), max(lo, hi)), 2)


def observable(p, value, base_props):
    """False when the value cannot work on this weapon: the clip must change after rounding and stay
    1..254 (m_iClip1 is an 8-bit network field), pellets must change and stay <= 64 traces per shot,
    ammo per shot must fit in the clip (else the weapon can never fire)."""
    s = SPEC.get(p["name"]) or {}
    clip = base_props.get("clip")
    if s.get("base") == "clip":
        if not clip or clip <= 0:
            return False
        n = int(clip * value + 0.5)
        return n != clip and 1 <= n <= 254
    if p["cls"] == "mult_bullets_per_shot":
        b = base_props.get("bullets") or 1
        n = int(b * value + 0.5)
        return n != b and n <= 64
    if p["cls"] == "mod_ammo_per_shot":
        return value <= (clip if clip and clip > 0 else 50)
    return True


# pairs that cancel or make each other do nothing on one weapon: never rolled together
CONFLICTS = [
    ({"crits_become_minicrits"}, {"minicrits_become_crits"}),
    ({"crit_airborne_simple"}, {"mini_crit_airborne"}),                     # the crit wins, the minicrit never shows
    ({"crit_on_objectives"}, {"mini_crit_on_objectives"}),
    ({"airblast_disabled", "set_flamethrower_push_disabled"},
     {"mult_airblast_cost", "apply_self_knockback_airblast", "airblast_destroy_projectile", "deflection_size_multiplier"}),
    ({"airblast_disabled"}, {"set_flamethrower_push_disabled"}),
    ({"no_self_blast_dmg"}, {"blast_dmg_to_self", "rocket_jump_dmg_reduction_weapon"}),
    ({"unimplemented_mod_sniper_no_charge"},                                # no zoom -> no charge, no scoped fire
     {"mult_sniper_charge_per_sec", "sniper_full_charge_damage_bonus", "mult_postfiredelay_scoped"}),
    ({"mod_ammo_per_shot"}, {"mult_clipsize"}),                             # a smaller clip could leave it unable to fire
    ({"set_detonate_mode"}, {"grenade_no_bounce"}),                         # fizzles on the first surface anyway
    ({"energy_weapon_no_ammo"}, {"mod_ammo_per_shot", "mult_clipsize"}),
    ({"mod_no_dmg_falloff"}, {"crit_dmg_falloff"}),                         # no falloff left for crits to follow
]


def conflicts(cls, used):
    """True when attribute class `cls` would cancel / be cancelled by one already rolled."""
    for a, b in CONFLICTS:
        if (cls in a and used & b) or (cls in b and used & a):
            return True
    return False
