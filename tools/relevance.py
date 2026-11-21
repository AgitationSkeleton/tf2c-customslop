"""What does an attribute actually affect, and does a given weapon provide it?

Every rollable attribute gets ONE "needs" tag from its attribute_class (the engine hooks by class,
not by name): what must be true of the item / wielder for it to do anything. A weapon provides a
set of tags from its item_class (5205 weapon mechanics), its family and the class wielding it.
An attribute is RELEVANT on a weapon iff its needs-tag is provided.

  needs "any"      player-level / generic weapon stat (damage, fire rate, speed, health, ...)
  needs "none"     no read site in the 2024 source nor its class string in 5205's server.dll,
                   Halloween-/bot-/MvM-only, or a mechanic no CustomSlop item can carry (banner,
                   lunchbox, shield charge, eyelander heads, energy weapons, ...): comedy only
  needs <mech>     a weapon mechanic (clip, bullets, projectile, explosive, rocket, sticky, flame,
                   airblast, melee, backstab, minigun, sniperrifle, headshot, medigun, ...)
  needs <class>    a class system any item worn by that class drives (engineer buildings/metal,
                   spy cloak/disguise, medic uber-on-hit, scout air jumps)

Rules are ordered regexes on attribute_class (first match wins); classes the rules don't know
fall back to their 2024 read-site files; anything still unknown counts as NOT relevant.
"""
import re

# (regex on attribute_class, needs)
RULES = [
    # reviewed 2026-11-20 against the read sites (attreffect.py): these act on the WIELDER / any target,
    # whatever the class - the generic regexes below would tie them to the Engineer / Medic / Sniper
    (r"^(mult_dmg_vs_buildings|mult_medigun_healing_received_active|mult_dispenser_healing_received_active|"
     r"mult_patient_overheal_penalty_active|dispenser_can_overheal_active|no_primary_ammo_from_dispensers|"
     r"mod_tranq_onhit|crit_airborne_simple)$", "any"),
    (r"^(headshot_damage_modify|headshot_is_minicrit)$", "headshot"),
    (r"^unimplemented_mod_sniper_no_charge$", "sniperrifle"),
    (r"^explosive_bullets$", "bullets"),
    (r"^(bot_|halloween_|hwn_|currency|powerup_|ragdolls_|player_skin|special_taunt|never_override_taunt|"
     r"enable_misc2|add_jingle|rocket_whistle|use_large_smoke|mod_never_draw_tracer|mod_always_draw_tracer|"
     r"add_player_capturevalue|set_turn_to_gold|set_watch_panel|provide_on_active|counts_as_assister|"
     r"crit_forces_victim_to_laugh|kill_forces_attacker_to_laugh|tickle_|fish_damage|set_silent_killer|"
     r"hide_ammo_hud|bullet_is_a_hull|mod_no_reload_display_only|unimplemented)", "none"),
    (r"(taunt|rage|buff_type|mod_buff_duration|banner)", "none"),                    # taunts, banner weapons
    (r"(lunchbox|sandvich|jarate_duration|mad_milk(?!_syringes)|throwable|brick)", "none"),
    (r"(charge_impact|charge_recharge|charge_turn|demo_charge|shield|charge_meter_on_hit|attack_not_cancel_charge|"
     r"set_charge_type|minicrit_boost_when_charged|minicrit_boost_charge_rate|chargeweapon_no_extra_speed|"
     r"movespeed_shieldrequired)", "none"),                                          # demo shield
    (r"(head_on_|decapitate|heads)", "none"),                                        # eyelander heads
    (r"(energy_weapon|hype|thermal_thruster|parachute|item_meter|effectbar|umbrella|generator|beacon)", "none"),
    (r"(mirv|cyclops|coil|throwingknife|paintball|tranq|taser|healimpact|heallauncher|healbomb|jumppad)", "none"),
    (r"^mad_milk_syringes$", "syringe"),
    # medic
    (r"(medigun|uberchargerate|overheal_uberchargerate|add_uber_time|ubercharge|healing_mastery|overheal_expert|"
     r"overheal_fill_rate|patient|boost_speed_from_patient|medic_healed|healrate|crit_heals_disabled|"
     r"bot_medic|enables_aoe_heal|mod_set_beam_range)", "medigun"),
    (r"^(add_onhit_ubercharge|subtract_victim_medigun)", "medic_or_any_hit"),
    # spy
    (r"(cloak|decloak|disguise|feign|set_blockbackstab|reveal_)", "spy"),
    (r"(backstab|back_?stab|stab_|freeze_backstab|set_disguise_on_backstab|sanguisuge|crit_from_behind)", "backstab"),
    # engineer
    (r"(sentry|dispenser|teleporter|building|construction|engy|metal|wrench_builds|mod_build_rate|"
     r"upgrade_rate_mod|mult_repair|arrow_heals_buildings|set_dmg_apply_to_sapper)", "engineer"),
    # pyro / fire
    (r"(airblast|deflect(?!_on_)|aoe_deflection|set_charged_airblast|redirected_flame|reflected_flame|"
     r"extinguish)", "airblast"),
    (r"(flame|ring_of_fire|set_flamethrower|axtinguisher)", "flame"),
    (r"^(set_dmgtype_ignite|afterburn_immunity|ignore_burn_immunity_self|explode_on_ignite)$|_self$", "any"),
    (r"(afterburn|burndmg|burntime|ignite|burn_)", "fire"),
    # heavy / sniper
    (r"(minigun|spinup|spunup|uses_ammo_while_aiming|aiming|flinch_resist_aiming)", "minigun"),
    (r"(sniper|zoom|scoped|bodyshot|mod_sniper|unimplemented_mod_sniper)", "sniperrifle"),
    (r"(headshot|can_headshot|back_headshot)", "headshot"),
    # demo / soldier
    (r"(sticky|stickies|pipebomb|proxymine|set_detonate_mode|detonat|add_max_pipebombs|fuse|grenade|bomblet)",
     "grenade_or_sticky"),
    (r"(rocket|blast_jump|rocketjump|mini_rockets|proj_detonate_with_rocket)", "rocket"),
    (r"(explosion|explosive|blast_dmg_to_self|no_self_blast|damage_blast_push|splash|disable_explosion_falloff)",
     "explosive"),
    # scout
    (r"(air_dash|scout_doublejump|scattergun)", "scout_or_scattergun"),
    # guns
    (r"(projectile|proj_|centerfire)", "projectile"),
    (r"(clip|reload|deploy_with_empty_clip|auto_fires)", "clip"),
    (r"(bullets_per_shot|spread|tracer|falloff|rampup|penetrat|fixed_shot_pattern|accuracy_scales|"
     r"punch_angle|mod_custom_falloff|mod_no_dmg)", "bullets"),
    (r"(maxammo_grenades|grenades\d_resupply)", "none"),                          # no grenade slots in 5205 play
    (r"(maxammo_primary|primary_ammo)", "ammo_primary"),                            # the wearer's primary weapon
    (r"(maxammo_secondary|secondary_ammo)", "ammo_secondary"),                      # the wearer's secondary weapon
    (r"(ammo|ammo_per_shot)", "ammo"),
    # melee
    (r"(melee|swing|smack|bash|deflect_on_|hit_self_on_miss|honorbound)", "melee"),
    # generic weapon / player effects
    (r"(dmgtaken|maxhealth|health_regen|movespeed|speed|jump|gravity|fall|healing_received|health_from|"
     r"health_frompacks|fromhealers|overheal_wearer|overheal_active|player_scale|voice_pitch|head_scale|hand_scale|"
     r"torso_scale|knockback|flinch|cancel_falling|air_control|deploy_time|holster|switch|no_duck|no_jump|"
     r"no_attack|crit_chance|postfiredelay|mult_dmg|dmg_vs|crit_vs|minicrit_vs|crit_on|crit_while|mini_crit|"
     r"crits_become|minicrits_become|critboost|onhit|on_hit|onkill|on_kill|lifesteal|heal_on|restore_health|"
     r"mark_for_death|bleeding|snare|stun|mult_onhit|armor_piercing|mod_outline|gain_stored_crits|"
     r"lose_stored_crits|always_crit|crit_does_no_damage|crit_kill_will_gib|no_crit_boost|or_crit|or_minicrit|"
     r"drop_health|drop_team|damage_all_connected|damage_causes_airblast|damage_force|apply_|weapon_enemy_knockback|"
     r"self_knockback|self_mark|mod_pierce_resists|force_weapon_switch|disable_weapon_switch|passive_reload|"
     r"weapon_blocks_healing|gesture_time|crit_dmg_falloff|mult_crit|dmg_from|everything_can_overheal|"
     r"health_kits_can_overheal|panic_attack|mult_dmg_penalty|boost_on_damage|melts_in_fire|"
     r"become_fireproof|weapon_range|set_weapon_range|customslop_)", "any"),
]

ITEM_TAGS = {   # 5205 item_class -> mechanics it provides
    "tf_weapon_rocketlauncher": {"rocket", "explosive", "projectile", "clip", "ammo"},
    "tf_weapon_grenadelauncher": {"grenade_or_sticky", "explosive", "projectile", "clip", "ammo"},
    "tf_weapon_pipebomblauncher": {"grenade_or_sticky", "explosive", "projectile", "clip", "ammo"},
    "tf2c_weapon_cyclops": {"grenade_or_sticky", "explosive", "projectile", "clip", "ammo"},
    "tf_weapon_flamethrower": {"flame", "airblast", "fire", "ammo"},
    "tf_weapon_flaregun": {"fire", "projectile", "ammo"},
    "tf_weapon_compound_bow": {"projectile", "ammo", "headshot"},
    "tf_weapon_syringegun_medic": {"projectile", "clip", "ammo", "syringe"},
    "tf2c_weapon_nailgun": {"projectile", "clip", "ammo"},
    "tf2c_weapon_coilgun": {"projectile", "clip", "ammo"},
    "tf2c_weapon_tranq": {"projectile", "clip", "ammo"},
    "tf_weapon_minigun": {"bullets", "ammo", "minigun"},
    "tf_weapon_sniperrifle": {"bullets", "ammo", "sniperrifle", "headshot"},
    "tf2c_weapon_hunting_revolver": {"bullets", "ammo", "clip", "headshot"},
    "tf_weapon_revolver": {"bullets", "ammo", "clip"},
    "tf_weapon_scattergun": {"bullets", "ammo", "clip", "scout_or_scattergun"},
    "tf2c_weapon_doubleshotgun": {"bullets", "ammo"},
    "tf2c_weapon_aagun": {"bullets", "ammo", "clip"},
    "tf_weapon_knife": {"melee", "backstab"},
}
FAMILY_TAGS = {
    "hitscan": {"bullets", "ammo", "clip"},
    "rocket": {"rocket", "explosive", "projectile", "clip", "ammo"},
    "grenade": {"grenade_or_sticky", "explosive", "projectile", "clip", "ammo"},
    "projectile": {"projectile", "clip", "ammo"},
    "flame": {"flame", "airblast", "fire", "ammo"},
    "melee": {"melee"},
}
CLASS_TAGS = {
    "Engineer": {"engineer"}, "Spy": {"spy"}, "Medic": {"medic_or_any_hit"}, "Scout": {"scout_or_scattergun"},
}
CLIPLESS = {"tf2c_weapon_doubleshotgun", "tf_weapon_minigun", "tf_weapon_flamethrower", "tf_weapon_sniperrifle",
            "tf_weapon_compound_bow"}

# class flavour: attribute classes that "feel like" the class (weighted up when also relevant)
FLAVOUR = {
    "Medic": r"heal|uber|overheal|regen|medic|patient|syringe",
    "Spy": r"cloak|backstab|stab|disguise|reveal|crit_from_behind|silent",
    "Engineer": r"sentry|dispenser|teleport|build|metal|construction|repair|wrench",
    "Pyro": r"flame|afterburn|burn|fire|airblast|ignite|deflect|extinguish",
    "Sniper": r"sniper|charge|headshot|zoom|scope|bodyshot|bleed",
    "Heavy": r"minigun|spin|aiming|maxhealth|health|dmgtaken|knockback",
    "Demoman": r"sticky|stickies|pipe|grenade|explosion|blast|detonat|fuse|splash",
    "Scout": r"speed|movespeed|jump|air_dash|dash|scattergun|onhit_enemyspeed|bleed",
    "Soldier": r"rocket|blast|explosion|jump|air_control|airborne|splash",
    "Civilian": r"speed|movespeed|health|dmgtaken|melee",
}


def needs(p, cat=None):
    """The needs-tag of a pool entry (p: attribute_pool_5205.json row)."""
    if p.get("vscript"):
        return "any"
    if not (p.get("in_5205") or p.get("read_2024")):
        return "none"
    cls = (p.get("cls") or "").lower()
    for rx, tag in RULES:
        if re.search(rx, cls):
            return tag
    files = (cat or {}).get(p.get("id"), {}).get("weapon_files") or []
    if files and all(f.startswith(("tf_weaponbase_melee",)) for f in files):
        return "melee"
    if files and all(f.startswith(("tf_weaponbase_gun", "tf_weaponbase_rocket")) for f in files):
        return "projectile" if any("rocket" in f for f in files) else "ammo"
    if files and any(f == "tf_weaponbase" for f in files):
        return "any"
    return "unknown"


def provides(item_class, family, classes, slot=None):
    t = {"any"} | set(FAMILY_TAGS.get(family, ())) | set(ITEM_TAGS.get(item_class, ()))
    if item_class in CLIPLESS:
        t.discard("clip")
    if family == "melee":
        t -= {"ammo", "clip", "bullets"}
    elif slot in ("primary", "secondary"):
        t.add("ammo_" + slot)
    for c in classes:
        t |= CLASS_TAGS.get(c, set())
    return t


def relevant(p, prov, cat=None):
    return needs(p, cat) in prov


def flavour(p, classes):
    cls = (p.get("cls") or "") + " " + (p.get("name") or "")
    return any(re.search(FLAVOUR[c], cls, re.I) for c in classes if c in FLAVOUR)
