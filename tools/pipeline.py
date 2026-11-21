"""CustomSlop per-weapon pipeline (offline): roll -> mutate -> recolour -> gate -> icon -> card.

make_weapon(defindex, rng, cfg, recipe) builds one complete weapon into <out_dir>:
  item.txt        schema item fragment (KeyValues), defindex = catalogue reservation
  summary.json    class(es), slot, base/donor, every attribute (name, class, value, disposition,
                  rendered TF2 line), mutation + recolour params, gate results, asset manifest
  files/...       game-path tree of every asset to ship (models/, materials/)
  icon.png        rendered icon (also files/materials/backpack/customslop/cs<id>_large.vtf/.vmt)
  render.png      model render (world model, same camera as the stock model)
  render_orig.png stock donor render for comparison
  card.png        TF2-style item card (fonts from the user's TF2 install)
Automatic safety (both modes): crash-safety clamps/whitelists (attrpool GUARDS), structural model
validation, a render-based quality gate; a failing weapon is re-rolled, never shipped.
"""
import collections
import json
import math
import os
import re
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths as P  # noqa: E402
import attrdesc  # noqa: E402
import attrpool  # noqa: E402
import card  # noqa: E402
import kv  # noqa: E402
import loc as LOC  # noqa: E402
import mutate as MU  # noqa: E402
import names  # noqa: E402
import recolor as RC  # noqa: E402
import render as RD  # noqa: E402
import srcmodel as S  # noqa: E402
import vfs as VFS  # noqa: E402
import vtf  # noqa: E402
import palette  # noqa: E402
import regions as REG  # noqa: E402
import sounds as sounds_mod  # noqa: E402
import validate_model as VM  # noqa: E402
import vmrender as VMR  # noqa: E402
import iconfit as IF  # noqa: E402
import labels  # noqa: E402
import relevance  # noqa: E402
import attrscope  # noqa: E402
import attreffect  # noqa: E402
import taunts  # noqa: E402
import slotrule  # noqa: E402
from generate import (CLASSES, CLASS_SLOTS, FAMILY, CLIPLESS, BASE_SCHEMA, AF_SCHEMA, load_schema)  # noqa: E402

POOL = os.path.join(ROOT, "analysis", "attribute_pool_5205.json")
OLDMERC = P.opt("oldmerc_dir")
B4 = P.opt("tf2classic_b4_dir")
CREDITS = {
    "tf2c": "TF2 Classified (TF2C team)",
    "aprilfools": "TF2 Classified April Fools 2026 pack (TF2C team)",
    "of_merc": "Open Fortress (Open Fortress team), staged by tf2cc",
    "marxvee": "MarxVee custom classes pack, staged by tf2cc",
    "presplit": "TF2C Presplit / TDC team (4dm/4rdm map paks)",
    "tf2classic_beta": "TF2 Classic team (2.0.0 betas)",
}
# item classes the engine-load test showed unusable as donors on build 5205
ENGINE_TEST_EXCLUDED = {"tf2c_weapon_nailgun": "server keeps the stock v_nailgun model (schema model_player "
                                               "not used) - engine-load test 2026-11-16"}
# individual donors excluded after review
DONOR_EXCLUDED = {"tf2classic_b4:90001": "translucent glass material + overlapping UV tiles: region recolour produces "
                                         "stripes and the look can't be verified offline (first-batch review 2026-11-16)",
                 "tf2classic_beta:30206": "tf2cc removed the 4rdm lead pipe (user decision 2026-11-16; OF has one)",
                 "tf2classic_beta:30223": "tf2cc removed the 4rdm Merc Twin Barrel copy (user decision 2026-11-16)"}
ITEM_CLASS_MAP = {"tf_weapon_smg_primary": "tf_weapon_smg", "tf_weapon_revolver_secondary": "tf_weapon_revolver",
                  "tf_weapon_heavyartillery": "tf_weapon_smg", "tf_weapon_hunterrifle": "tf_weapon_sniperrifle",
                  "tf_weapon_umbrella": "tf2c_weapon_umbrella", "tf_weapon_shotgun_soldier": "tf_weapon_shotgun",
                  "tf_weapon_shotgun_primary": "tf_weapon_shotgun"}
DEFAULT_CLASS = {"tf_weapon_scattergun": "Scout", "tf_weapon_bat": "Scout", "tf_weapon_pistol": "Engineer",
                 "tf_weapon_shotgun": "Engineer", "tf_weapon_rocketlauncher": "Soldier", "tf_weapon_shovel": "Soldier",
                 "tf_weapon_flamethrower": "Pyro", "tf_weapon_fireaxe": "Pyro", "tf_weapon_flaregun": "Pyro",
                 "tf_weapon_grenadelauncher": "Demoman", "tf_weapon_pipebomblauncher": "Demoman", "tf_weapon_bottle": "Demoman",
                 "tf_weapon_minigun": "Heavy", "tf_weapon_fists": "Heavy", "tf_weapon_wrench": "Engineer",
                 "tf_weapon_syringegun_medic": "Medic", "tf_weapon_bonesaw": "Medic", "tf_weapon_sniperrifle": "Sniper",
                 "tf_weapon_smg": "Sniper", "tf_weapon_club": "Sniper", "tf_weapon_revolver": "Spy", "tf_weapon_knife": "Spy",
                 "tf2c_weapon_umbrella": "Civilian", "tf2c_weapon_nailgun": "Scout", "tf_weapon_compound_bow": "Sniper"}
PROJ_MODELS = os.path.join(ROOT, "analysis", "projectile_model_candidates.json")
TEX_MAX = 256          # user decision 2026-11-16: CustomSlop weapons are temporary - small textures
SIZE_CAP_BZ2 = 1024 * 1024   # user decision: <= 1 MB bz2 per weapon (models + textures + icon)
TYPE_NAMES = {"tf_weapon_pipebomblauncher": "Stickybomb Launcher", "tf_weapon_grenadelauncher": "Grenade Launcher",
              "tf_weapon_rocketlauncher": "Rocket Launcher", "tf_weapon_syringegun_medic": "Syringe Gun",
              "tf_weapon_flamethrower": "Flame Thrower", "tf_weapon_sniperrifle": "Sniper Rifle"}
ICON_SIZE = 256        # loadout/HUD icon texture (rendered at 512, downsampled; the panel scales it)


def known_killicons(fs, server_root):
    """Kill-icon names the 5205 client can draw: deathnotice SVGs in the game VPKs, in the server's
    resource/ folder, and those a server plugin downloads (addons/sourcemod/configs/*/downloads*.txt)."""
    import glob
    names = set()
    for kind, path in VFS.DEFAULT_ORDER:
        if kind == "vpk" and os.path.exists(path):
            names |= {os.path.basename(n)[:-4].lower() for n in VFS.VPK(path).ents
                      if n.startswith("resource/svgs/deathnotice/") and n.endswith(".svg")}
    if server_root:
        for dp, _, fs_ in os.walk(os.path.join(server_root, "resource", "svgs", "deathnotice")):
            names |= {f[:-4].lower() for f in fs_ if f.endswith(".svg")}
        for p in glob.glob(os.path.join(server_root, "addons", "sourcemod", "configs", "*", "downloads*.txt")):
            names |= {m.lower() for m in re.findall(r"resource/svgs/deathnotice/([^/\s]+)\.svg",
                                                   open(p, encoding="utf-8", errors="replace").read())}
    return names


class Ctx:
    """Shared, loaded once: VFS, localisation, attribute pool, schema defs, donors, fonts."""

    def __init__(self, cfg, audit=True):
        self.cfg = cfg
        self.fs = VFS.VFS()
        self.L = LOC.Loc()
        self.pool = [p for p in json.load(open(POOL)) if p["disposition"] != "excluded"]
        base = load_schema(BASE_SCHEMA)
        self.defs = attrdesc.defs_from_schema(base)
        for p in json.load(open(POOL)):
            if p.get("vscript"):
                self.defs[p["name"].lower()] = dict(name=p["name"], desc_text=p["desc_text"], fmt=p["fmt"],
                                                    effect=p["effect"], hidden=False)
        self.fonts = card.find_fonts(cfg.get("fonts_dir"))
        self.proj_models = [m for m in json.load(open(PROJ_MODELS)) if "skybox" not in m and "/effects/" not in m]
        self.donors = self._donors()
        # kill icons: keep a donor's item_iconname only if the client can draw it (TF2C 5205 death
        # notices are resource/svgs/deathnotice/<name>.svg: stock ones + those tf2cc downloads)
        self.killicons = known_killicons(self.fs, cfg.get("server_root"))
        for d in self.donors:
            ic = d["kv"].get("item_iconname")
            if ic and ic.lower() not in self.killicons:
                d["kv"] = kv.KV([(k, v) for k, v in d["kv"].pairs if k.lower() != "item_iconname"])
        self.audit = {}
        ap = os.path.join(ROOT, "cache", "donor_audit.json")
        if audit and os.path.exists(ap):
            self.audit = json.load(open(ap))
            self.donors = [d for d in self.donors if self.audit.get("%s:%s" % (d["src"], d["id"]), {}).get("ok", True)]
        self.sounds = sounds_mod.Picker()
        try:
            self.attr_scope, self.attr_links = attrscope.load()
        except Exception:                # no scope analysis: no gate (tools/attrscope.py builds it)
            self.attr_scope, self.attr_links = None, {}
        cat_p = os.path.join(os.path.dirname(POOL), "attributes_5205.json")
        self.attr_cat = {r["id"]: r for r in json.load(open(cat_p))} if os.path.exists(cat_p) else {}
        # item_type_name tokens must resolve in TF2C's OWN localisation (not TF2's): labels.py
        self.tf2c_tokens = labels.tf2c_tokens(cfg.get("server_root") or P.server_root())
        self.stock_types = labels.stock_types(load_schema(BASE_SCHEMA), self.tf2c_tokens)
        # what build 5205's schema loader accepts (see validate_model.schema_check)
        ig = load_schema(BASE_SCHEMA)
        self.schema_defs = {a.get("name").lower(): dict(integer=a.get("stored_as_integer") == "1",
                                                        set_bonus=a.get("is_set_bonus") == "1",
                                                        string=a.get("attribute_type") == "string")
                            for _, a in ig.get("attributes").blocks() if a.get("name")}
        self.item_classes = {it.get("item_class") for path in (BASE_SCHEMA, AF_SCHEMA)
                             for _, it in load_schema(path).get("items").blocks() if it.get("item_class")}
        # + classes reached through prefabs: any weapon entity class name compiled into 5205's server.dll
        sv = set(open(P.data("server_strings.txt"),
                      encoding="latin-1", errors="replace").read().split("\n"))
        self.item_classes |= {c for fam in FAMILY.values() for c in fam if c in sv}
        self.avoid_hues = [h for _, h in cfg.get("_used_hues", [])[-12:]]
        # CustomSlop-owned attribute definitions (ids 25900+, persisted in the catalogue): the
        # VScript effects plus "display fixes" - an existing attribute_class re-declared with the
        # description format that makes the TF2/TF2C text read true for the rolled value
        self.attr_registry = cfg.get("_attr_registry", {})       # name -> {id, cls, fmt, effect, desc}

    def fixed_def(self, p):
        name = "customslop " + p["name"].lower()
        if name not in self.attr_registry:
            used = {d["id"] for d in self.attr_registry.values()} | {25900}
            nid = max(used) + 1
            flip = {"value_is_percentage": "value_is_inverted_percentage",
                    "value_is_inverted_percentage": "value_is_percentage"}[p["fmt"]]
            self.attr_registry[name] = dict(id=nid, cls=p["cls"], fmt=flip, effect=p["effect"], desc=p["desc_token"],
                                            desc_text=p["desc_text"])
        d = self.attr_registry[name]
        self.defs[name] = dict(name=name, desc_text=d["desc_text"], fmt=d["fmt"], effect=d["effect"], hidden=False)
        return name

    def _donors(self):
        """Every donor source (read-only; CustomSlop ships its own mutated copies under its own paths):
        TF2C stock, April Fools 2026, tf2cc's Open Fortress Merc + MarxVee items, the old TF2 Classic
        Merc / presplit (4dm/4rdm) / beta weapons staged by tf2cc's oldmerc research, and the TF2
        Classic 2.0.0 beta 4 items. Each donor records its source credit."""
        out = []

        def add(src, did, it, ic, slot, classes, mp, mw, fs, credit, kvsrc=None):
            ic = ITEM_CLASS_MAP.get(ic, ic)
            if "%s:%s" % (src, did) in skip_keys:
                self.donor_skips.append((src, did, ic, DONOR_EXCLUDED["%s:%s" % (src, did)]))
                return
            if ic in ENGINE_TEST_EXCLUDED:
                self.donor_skips.append((src, did, ic, ENGINE_TEST_EXCLUDED[ic]))
                return
            fam = next((f for f, s_ in FAMILY.items() if ic in s_), None)
            if not fam or not mp or fs.read(mp) is None:
                self.donor_skips.append((src, did, ic, "no family" if not fam else "model missing"))
                return
            if not classes:
                classes = [DEFAULT_CLASS.get(ic, "Soldier")]
            classes = [c.capitalize() for c in classes if c.capitalize() in CLASSES] or [DEFAULT_CLASS.get(ic, "Soldier")]
            if it is None:
                it = kv.KV()
            # the emitted item must use a 5205 item class (b4/oldmerc names are mapped), so the
            # donor's KV is copied with item_class replaced - the donor's own data is never edited
            it = kv.KV([(k_, v_) for k_, v_ in it.pairs if k_.lower() != "item_class"] + [("item_class", ic)])
            out.append(dict(src=src, id=did, kv=it, fam=fam, slot=slot, classes=classes, mp=mp,
                            mw=mw if mw and fs.read(mw) is not None else None, fs=fs, credit=credit))
        self.donor_skips = []
        skip_keys = set(DONOR_EXCLUDED)
        for src, path, credit in (("tf2c", BASE_SCHEMA, CREDITS["tf2c"]), ("aprilfools", AF_SCHEMA, CREDITS["aprilfools"])):
            for k, it in load_schema(path).get("items").blocks():
                if not k.isdigit() or (src == "aprilfools" and not 17500 <= int(k) <= 17519):
                    continue  # only the April Fools items from the live merged file, never tf2cc's
                ubc = it.get("used_by_classes")
                add(src, int(k), it, it.get("item_class") or "", it.get("item_slot"),
                    [c for c, _ in ubc.pairs] if isinstance(ubc, kv.KV) else [], it.get("model_player"),
                    it.get("model_world"), self.fs, credit)
        tc = load_schema(AF_SCHEMA).get("items")          # the live merged file also holds tf2cc's items
        for k, it in tc.blocks():
            if k.isdigit() and 30100 <= int(k) <= 30151:
                src = "marxvee" if int(k) >= 30150 else "of_merc"
                add(src, int(k), it, it.get("item_class") or "", it.get("item_slot"), [], it.get("model_player"),
                    it.get("model_world"), self.fs, CREDITS[src])
        tc_icons = {(it.get("model_player") or "").lower(): it.get("item_iconname") for k, it in tc.blocks()
                    if k.isdigit() and it.get("item_iconname")}
        tc_names = {(it.get("model_player") or "").lower(): it.get("item_name") for k, it in tc.blocks()
                    if k.isdigit() and it.get("item_name")}
        om = os.path.join(OLDMERC or "", "oldmerc_items.json")
        if os.path.exists(om):
            ofs = VFS.VFS([("dir", os.path.join(OLDMERC, "staging", "tf2classified"))] + VFS.DEFAULT_ORDER)
            for x in json.load(open(om))["items"]:
                s_ = x.get("source", "")
                src = "tf2classic_beta" if re.search(r"\bb[24]\b|_b[24]|beta", s_ + x["model_player"]) else "presplit"
                # tf2cc's oldmerc research: L4D-style viewmodels (attach_to_hands 2) except the old
                # chainsaw (hands baked in, 0). Without this key 5205 keeps the base weapon's model
                # (caught by the engine-load test).
                okv = kv.KV([("attach_to_hands", "0" if "chainsaw" in x["model_player"] else "2")])
                # kill icon: the one the CURRENT tf2cc base gives the item with this model (user: kill
                # icons must match the donor model's own, e.g. tf2cc_merc_stengun_v1)
                nm_ = x.get("item_name") or tc_names.get(x["model_player"].lower())
                if nm_:
                    okv.add("item_name", nm_)        # display name (item_type_name subtext)
                ic_ = tc_icons.get(x["model_player"].lower())
                if ic_:
                    okv.add("item_iconname", ic_)
                add(src, x["id"], okv, x.get("base") or "", x.get("slot"), [], x["model_player"], x.get("model_world"),
                    ofs, CREDITS[src])
        if B4 and os.path.isdir(B4):
            bfs = VFS.VFS([("dir", B4)] + VFS.DEFAULT_ORDER)
            for k, it in kv.load(os.path.join(B4, "scripts", "items", "items_game.txt"))[0].get("items_game").get("items").blocks():
                mp = it.get("model_player")
                if not k.isdigit() or not mp or not os.path.exists(os.path.join(B4, mp)):
                    continue                             # only models that differ from TF2C's (present in b4)
                ubc = it.get("used_by_classes")
                ic = it.get("item_class") or ("tf_weapon_shotgun" if "shotgun" in mp else "")
                add("tf2classic_b4", 90000 + int(k), it, ic, it.get("item_slot"),
                    [c for c, _ in ubc.pairs] if isinstance(ubc, kv.KV) else [], mp, it.get("model_world"), bfs,
                    CREDITS["tf2classic_beta"])
        return out


# ---------------------------------------------------------------- attribute rolling
HIGHER_IS_WORSE = re.compile(r"^(mult_postfiredelay|mult_reload_time|mult_deploy_time|mult_switch_from_wep_deploy_time|"
                             r"mult_spread_scale|mult_dmgtaken|mult_minigun_spinup_time|mult_flame_ammopersec|"
                             r"mult_cloak_meter_consume|mult_gesture_time_penalty|mult_dmg_falloff_unused|mult_single_wep_deploy_time|"
                             r"mult_airblast_cost|rocket_jump_dmg_reduction|stickybomb_charge_rate|mult_postfiredelay_scoped)")
HIGHER_IS_BETTER = re.compile(r"^(mult_dmg$|mult_dmg_vs|mult_clipsize|mult_maxammo|mult_projectile_speed|mult_explosion_radius|"
                              r"mult_bullets_per_shot|mult_player_movespeed|mult_health|mult_heal|mult_medigun|"
                              r"mult_cloak_meter_regen|mult_sniper_charge|mult_engy|mult_sentry|mult_projectile_range|"
                              r"mult_wpn_burn|mult_charge|mult_flame_size|mult_player_aiming_movespeed|mult_construction_value|"
                              r"mult_repair_value|effectbar_recharge_rate)")


def semantic_side(p):
    """'up'/'down' = side of 1.0 the value must be on for this definition's effect_type, when the
    mechanics of the attribute class are known; None otherwise."""
    c, eff = p["cls"] or "", p["effect"]
    if eff not in ("positive", "negative"):
        return None
    if HIGHER_IS_WORSE.search(c):
        return "down" if eff == "positive" else "up"
    if HIGHER_IS_BETTER.search(c):
        return "up" if eff == "positive" else "down"
    return None


def safety_range(p):
    """(lo, hi) multiplier bounds for a multiplicative class: engine/crash safety only
    (attrpool.GUARDS clamps), else DEFAULT_MULT_RANGE."""
    for rx, kind, par in attrpool.GUARDS:
        if kind == "clamp" and re.search(rx, p["cls"] or ""):
            return par[0], par[1]
    return DEFAULT_MULT_RANGE


def guard(p, v):
    """Crash-safety clamps (attrpool.GUARDS) - applied to every rolled value, whatever rolled it."""
    for rx, kind, par in attrpool.GUARDS:
        if kind == "clamp" and re.search(rx, p["cls"] or "") and isinstance(v, (int, float)):
            v = min(max(v, par[0]), par[1])
    return v


DEFAULT_MULT_RANGE = (0.05, 10.0)   # multipliers no guard covers: float scales, nothing divides by them
MIN_EFFECT = 0.05                   # a multiplier within 5% of 1.0 would not do anything noticeable


def roll_value(p, rng, extreme=False, mild=False):
    """Uniform over the definition's whole working range on the side its text requires
    (standing rule, user 2026-11-20: "truly random" so long as the item works and does what it
    says; extreme/mild are ignored - kept only for old callers). Multipliers: side of 1.0 from the
    mechanics when known (semantic_side), else from the displayed sign; range = the class's
    crash-safety bounds, starting MIN_EFFECT away from 1.0."""
    fmt, dirn = p["fmt"], p["direction"]
    s = (p.get("desc_text") or "")
    if dirn == "flag":
        v = 1
    else:
        sign = 1 if dirn == "pos" else -1
        sem = semantic_side(p)
        if fmt in ("value_is_percentage", "value_is_inverted_percentage"):
            if sem:
                up = sem == "up"
            else:
                up = (sign > 0) == (fmt == "value_is_percentage")
            lo, hi = safety_range(p)
            v = round(rng.uniform(1.0 + MIN_EFFECT, hi), 2) if up else round(rng.uniform(lo, 1.0 - MIN_EFFECT), 2)
        elif fmt == "value_is_additive_percentage":
            v = sign * round(rng.uniform(0.01, 1.0), 2)
        else:
            if re.search(r"second", s, re.I):
                m = round(rng.uniform(0.5, 30), 1)
            elif re.search(r"health|hp\b", s, re.I):
                m = rng.randint(1, 300)
            elif "%" in s:
                m = rng.randint(1, 100)
            else:
                m = rng.randint(1, 10)
            # a template that carries its own sign ("Per Shot: -%s1 ammo") takes the magnitude
            v = m if re.search(r"[-+]%s1", s) else sign * m
    if p.get("integer"):
        v = int(round(v))
    return guard(p, v)


def roll_attributes_v1(ctx, rng, fam, slot, recipe, item_class=None, classes=()):
    """The original roller (uniform over ~840 attributes): kept only as the report baseline."""
    want = recipe.get("n_attr") or rng.randint(3, 7)
    chosen, classes = [], set()
    cands = [p for p in ctx.pool if not p["cls"].startswith(("override_projectile_type", "custom_projectile_model"))]
    if fam not in ("rocket", "grenade", "projectile"):
        cands = [p for p in cands if not re.search(r"projectile|explosion|blast|sticky|pipe", p["cls"])]
    if fam == "melee":
        cands = [p for p in cands if not re.search(r"clip|reload|ammo|spread|bullets", p["cls"])]

    def weight(p):
        w = p["weight"].get(fam, 0.25)
        if p["hidden"]:
            w *= 0.35
        if not p.get("desc_text"):
            w *= 0.6
        return w

    def take(p):
        chosen.append(p)
        classes.add(p["cls"])

    for _ in range(recipe.get("mvm", 0)):
        m = [p for p in cands if p["mvm"] and p["cls"] not in classes]
        if m:
            take(m[rng.randrange(len(m))])
    for c in recipe.get("force", []):
        m = [p for p in cands if p["cls"] == c and p["cls"] not in classes]
        if m:
            take(m[0])
    while len(chosen) < want:
        rest = [p for p in cands if p["cls"] not in classes]
        ws = np.array([weight(p) for p in rest])
        take(rest[int(rng.choices(range(len(rest)), weights=ws)[0])])
    return finish_attributes(ctx, rng, chosen, fam, recipe)


def finish_attributes(ctx, rng, chosen, fam, recipe, mild=False, big=()):
    out = []
    for p in chosen:
        v = attreffect.roll(p, rng)
        v = roll_value(p, rng) if v is None else guard(p, v)
        props = getattr(ctx, "_weapon_props", None)
        if props is not None and not attreffect.observable(p, v, props):
            for _ in range(40):                        # clip / pellets / ammo per shot must work here
                v = guard(p, attreffect.roll(p, rng))
                if attreffect.observable(p, v, props):
                    break
            else:
                continue
        name = p["name"]
        # values with known mechanics follow the mechanics; TF2's own format then shows them as the
        # game would. Only a negative number in front of magnitude wording ("-50% slower") reads
        # wrong - then use a CustomSlop re-declaration of the same class with the flipped format.
        if p["fmt"] in ("value_is_percentage", "value_is_inverted_percentage") and semantic_side(p) \
                and not p["hidden"] and p.get("desc_text"):
            n = attrdesc.value_for(p["fmt"], v)
            if n < 0 and attrpool.MAGNITUDE_WORDS.search(p["desc_text"]):
                name = ctx.fixed_def(p)          # same attribute_class, flipped format: text reads true
        out.append(dict(name=name, cls=p["cls"], value=v, disposition=p["disposition"], mvm=p["mvm"],
                        hidden=p["hidden"], read=p["read_2024"] or p["in_5205"], base_def=p["name"]))
    if recipe.get("proj_model") and fam in ("rocket", "grenade"):
        out.append(dict(name="custom projectile model", cls="custom_projectile_model",
                        value=rng.choice(ctx.proj_models), disposition="guarded", mvm=False, hidden=True, read=True))
    return out


# roller (v2). Standing rule (user 2026-11-20): "truly random" so long as the item works and does
# what it says. The only constraints are ones an item needs to WORK: the stat is read for this item
# class (attrscope source gate), it is on the reviewed whitelist (attreffect: visible, right sign,
# an effect at the rolled value, applies to this item class), its mechanic exists for the wielding
# class (relevance needs/provides: e.g. cloak only does something for a Spy), one definition per
# attribute class (two would stack into one number), no conflicting/cancelling pair
# (attreffect.CONFLICTS), at most JOKE_MAX deliberate jokes. No weights, no forced upside/downside.
N_ATTR = (3, 6)          # stats per weapon, uniform (unchanged range)
# a missing weapon mechanic / class system makes a stat provably inert (no clip -> clip stats do
# nothing, not a Spy -> no cloak); generic tags ("any", "fire", "unknown") don't, so never jokes
JOKE_INERT_TAGS = {"spy", "engineer", "medigun", "minigun", "sniperrifle", "scout_or_scattergun", "flame", "airblast",
                   "grenade_or_sticky", "rocket", "melee", "clip", "bullets", "projectile", "explosive", "headshot",
                   "backstab", "ammo", "syringe"}


def roll_attributes(ctx, rng, fam, slot, recipe, item_class=None, classes=()):
    """Attributes for one weapon: uniformly random working stats + 0..JOKE_MAX jokes (see above)."""
    if recipe.get("algo") == "v1":
        return roll_attributes_v1(ctx, rng, fam, slot, recipe, item_class, classes)
    classes = list(classes)
    prov = relevance.provides(item_class or "", fam, classes, slot)
    want = recipe.get("n_attr") or rng.randint(*N_ATTR)
    comedy = recipe.get("comedy")
    if comedy is None:
        comedy = rng.randint(0, attreffect.JOKE_MAX)
    comedy = min(int(comedy), attreffect.JOKE_MAX, want)
    ctx._weapon_props = weapon_props(ctx, item_class, classes)
    every = [p for p in ctx.pool if not p["cls"].startswith(("override_projectile_type", "custom_projectile_model"))]
    vs = lambda p: bool(p.get("vscript") and ctx.cfg.get("vscript_installed"))          # noqa: E731
    cands = every
    if ctx.attr_scope is not None:      # read on this weapon / the active weapon, for this item class
        cands = [p for p in cands if vs(p) or attrscope.works_on(ctx.attr_scope.get(p["cls"]), item_class, ctx.attr_links)]
    cands = [p for p in cands if vs(p) or attreffect.allowed(p, item_class)]            # reviewed whitelist
    nd = {id(p): relevance.needs(p, ctx.attr_cat) for p in cands}
    rel = [p for p in cands if nd[id(p)] in prov]                                        # mechanic exists
    by_cls = {}
    for p in rel:
        by_cls.setdefault(p["cls"], []).append(p)
    chosen, used = [], set()

    def free(c):
        return c not in used and not attreffect.conflicts(c, used)

    def take(p):
        chosen.append(p)
        used.add(p["cls"])

    for c in recipe.get("force", []):                    # explicit recipe (first-deploy / tests only)
        m = [p for p in cands if p["cls"] == c and free(c)]
        if m:
            take(m[0])
    for _ in range(recipe.get("mvm", 0)):
        m = [p for p in rel if p["mvm"] and free(p["cls"])]
        if m:
            take(m[rng.randrange(len(m))])
    while len(chosen) < want - comedy:
        open_ = sorted(c for c in by_cls if free(c))
        if not open_:
            break
        defs = by_cls[open_[rng.randrange(len(open_))]]  # uniform over attribute classes, then over
        take(defs[rng.randrange(len(defs))])             # that class's definitions (bonus / penalty)
    jokes = []
    if comedy:
        # deliberate jokes: a reviewed, visible stat that is provably INERT here - weapon-scoped (never
        # read on the player, so it cannot leak onto other weapons) and either not read for this item
        # class at all, or for a mechanic this weapon/class doesn't have ("+30% sentry damage" on a
        # rocket launcher). Marked joke=True in the summary.
        jp = []
        for p in every:
            if p.get("vscript") or not attreffect.SPEC.get(p["name"]) or p["hidden"] or not p.get("desc_text"):
                continue
            info = ctx.attr_scope.get(p["cls"]) if ctx.attr_scope is not None else None
            if not info or info["verdict"] != "safe":
                continue
            works = attrscope.works_on(info, item_class, ctx.attr_links) and attreffect.allowed(p, item_class)
            need = relevance.needs(p, ctx.attr_cat)
            if not works or (need not in prov and need in JOKE_INERT_TAGS):
                jp.append(p)
        for _ in range(comedy):
            q = [p for p in jp if free(p["cls"])]
            if not q:
                break
            j = q[rng.randrange(len(q))]
            take(j)
            jokes.append(j)
    out = finish_attributes(ctx, rng, chosen, fam, recipe)
    by_name = {}
    for p in chosen:
        by_name.setdefault(p["name"], p)
    joke_ids = {id(p) for p in jokes}
    for a in out:
        p = by_name.get(a.get("base_def") or a["name"])
        if p is None:
            continue
        a["needs"] = nd.get(id(p)) or relevance.needs(p, ctx.attr_cat)
        a["relevant"] = a["needs"] in prov
        a["joke"] = id(p) in joke_ids
    return out


def weapon_props(ctx, item_class, classes):
    """clip / bullets per shot from the 5205 weapon script of the entity the item really is."""
    ent = item_class or ""
    try:
        if classes:
            ent = taunts.entity(item_class, sorted(classes)[0]) or ent
    except Exception:
        pass
    out = {}
    for nm in (ent, item_class or ""):
        d = ctx.fs.read("scripts/%s.txt" % nm) if nm else None
        if d is None:
            continue
        t = d.decode("latin-1")
        m = re.search(r'"?clip_size"?\s+"?(-?\d+)', t, re.I)
        b = re.search(r'"?BulletsPerShot"?\s+"?(\d+)', t, re.I)
        out = dict(clip=int(m.group(1)) if m else None, bullets=int(b.group(1)) if b else 1)
        break
    return out


# ---------------------------------------------------------------- assets
def resolve_vmt(ctx, model, tex):
    for cd in model.cdmaterials:
        rel = "materials/" + re.sub("/+", "/", (cd + tex).replace(chr(92), "/")).lstrip("/").lower() + ".vmt"
        d = ctx.fs.read(rel)
        if d is not None:
            t = d.decode("latin-1")
            if re.match(r'\s*"?patch"?', t, re.I):          # Patch: take the included material's body
                inc = re.search(r'"?include"?\s+"([^"]+)"', t, re.I)
                if inc:
                    base = ctx.fs.read(inc.group(1).replace("\\", "/"))
                    if base is not None:
                        b = base.decode("latin-1")
                        for k, v in re.findall(r'"(\$[^"]+)"\s+"([^"]*)"', t):
                            b = re.sub(r'("%s"\s+)"[^"]*"' % re.escape(k), lambda mm: mm.group(1) + '"%s"' % v, b, flags=re.I) \
                                if re.search(re.escape(k), b, re.I) else b.replace("{", '{\n\t"%s" "%s"' % (k, v), 1)
                        t = b
            return rel, t
    return None, None


def recolour_model_textures(ctx, model, out_files, matdir, op, done):
    """For every texture the model names: copy its VMT into matdir with a recoloured basetexture."""
    for tex in model.textures:
        rel, t = resolve_vmt(ctx, model, tex)
        if not t:
            continue
        mm = re.search(r'"\$basetexture"\s+"([^"]+)"', t, re.I)
        if not mm:
            continue
        bt = mm.group(1).replace("\\", "/").lower()
        if bt not in done:
            raw = ctx.fs.read("materials/" + bt + ".vtf")
            if raw is None:
                continue
            w, h, img, info = vtf.decode(raw)
            if max(w, h) > TEX_MAX:
                k = TEX_MAX / max(w, h)
                img = np.asarray(Image.fromarray(img, "RGBA").resize((int(w * k), int(h * k)), Image.LANCZOS))
            rgb = img[..., :3].astype(np.float32) / 255
            out = RC.hsv_transform(rgb, **op["global"])
            if op.get("mask") is not None and op["mask"].shape[:2] == img.shape[:2]:
                m = op["mask"][..., None]
                out = out * (1 - m) + RC.hsv_transform(out, **op["section"]) * m
            res = np.dstack([(out * 255 + .5).astype(np.uint8), img[..., 3]])
            name = "%s_%d" % (os.path.basename(bt), len(done))
            dst = os.path.join(out_files, "materials", matdir, name + ".vtf")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            fmt = 13 if res[..., 3].min() >= 250 else 15      # DXT1 unless the alpha channel is used
            open(dst, "wb").write(vtf.encode(res, fmt=fmt, mips=info["mips"] > 1, flags=info["flags"] & ~0x4000))
            done[bt] = matdir + "/" + name
        t2 = re.sub(r'("\$basetexture"\s+)"[^"]*"', lambda m_: m_.group(1) + '"%s"' % done[bt], t, flags=re.I)
        vp = os.path.join(out_files, "materials", matdir, tex.lower() + ".vmt")
        os.makedirs(os.path.dirname(vp), exist_ok=True)
        open(vp, "w", encoding="latin-1").write(t2)


def extract_model(ctx, rel, dst_dir):
    base = rel[:-4]
    got = []
    for ext in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
        d = ctx.fs.read(base + ext)
        if d is not None:
            p = os.path.join(dst_dir, base.replace("/", os.sep) + ext)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(d)
            got.append(p)
    return os.path.join(dst_dir, rel.replace("/", os.sep))


def quality_gate(orig_img, new_img):
    """Render-based gate: silhouette area within x0.4..x3 of the stock model's, no large new
    near-black regions (faceting / exposed interiors), something visible at all."""
    a0 = np.asarray(orig_img)[..., 3] > 128
    a1 = np.asarray(new_img)[..., 3] > 128
    if a1.sum() < 500:
        return False, "empty render"
    ratio = a1.sum() / max(1, a0.sum())
    lum0 = np.asarray(orig_img)[..., :3].mean(-1)
    lum1 = np.asarray(new_img)[..., :3].mean(-1)
    dark0 = (lum0[a0] < 12).mean() if a0.any() else 0
    dark1 = (lum1[a1] < 12).mean()
    # fragmentation: a mutation must not split the weapon into floating shards / spikes
    c0, c1 = blobs(a0), blobs(a1)
    spiky = thinness(a1) - thinness(a0)
    ok = 0.4 <= ratio <= 3.0 and dark1 - dark0 < 0.05 and c1 <= c0 + 1 and spiky < 0.02
    return bool(ok), "area x%.2f, near-black %.3f -> %.3f, pieces %d -> %d, thin-edge %+.3f" % (
        ratio, dark0, dark1, c0, c1, spiky)


def blobs(mask, min_px=40):
    """Connected silhouette pieces (4-connected) larger than min_px, at 128 px."""
    from PIL import Image as _I
    m = np.asarray(_I.fromarray((mask * 255).astype(np.uint8)).resize((128, 128), _I.NEAREST)) > 127
    lab = np.zeros(m.shape, int)
    n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1
        stack, size = [(y0, x0)], 0
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            size += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < 128 and 0 <= xx < 128 and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
        if size < min_px:
            n -= 0          # tiny specks are counted below
            lab[lab == n] = -1
    return len([k for k in np.unique(lab) if k > 0])


def thinness(mask):
    """Share of silhouette pixels that vanish after a 2-px erosion (slivers, spikes)."""
    from PIL import Image as _I, ImageFilter as _F
    im = _I.fromarray((mask * 255).astype(np.uint8))
    er = np.asarray(im.filter(_F.MinFilter(5))) > 127
    return float(1 - er.sum() / max(1, mask.sum()))


WHACKY = {   # effect -> (mild, extreme) strength range; applied past the pivot, grip always protected
    "droop": (0.08, 0.45), "twist": (25, 160), "bend": (10, 45), "flare": (0.5, 2.6),
    "distend": (0.35, 1.4), "squash": (1.25, 2.4), "wobble": (0.01, 0.05), "stretch": (1.15, 2.1),
}
AFFINE_SAFE = ("stretch", "squash", "droop", "distend")   # what coarse meshes get (piecewise-affine)


def mesh_params(rng, recipe, attempt, coarse=False):
    extreme = recipe.get("extreme")
    pool = list(AFFINE_SAFE if coarse else WHACKY)
    k = rng.choice([1, 2, 2, 3]) if attempt == 0 else 1
    p = dict(pivot=round(rng.uniform(0.3, 0.55), 2),
             parts=dict(seed=rng.randrange(1 << 30), scale=[0.55, 1.9] if extreme else [0.7, 1.5],
                        fraction=round(rng.uniform(0.3, 0.8), 2)), effects=[])
    for eff in rng.sample(pool, k):
        lo, hi = WHACKY[eff]
        x = rng.uniform(lo, hi) if extreme or rng.random() < 0.5 else rng.uniform(lo, (lo + hi) / 2)
        x = x * (0.6 if attempt == 1 else 1.0)          # second attempt: tone it down
        sign = rng.choice([-1, 1])
        if eff == "droop":
            p["droop"] = round(x, 3)
        elif eff == "twist":
            p["twist"] = round(sign * x, 1)
        elif eff == "bend":
            p.update(bend=round(sign * x, 1), bend_plane=rng.choice([0, 90, 45]))
        elif eff == "flare":
            p["flare"] = round(x, 2)
        elif eff == "distend":
            p.update(bulge=round(x, 2), bulge_at=round(rng.uniform(0.55, 0.9), 2), bulge_width=round(rng.uniform(0.06, 0.14), 2))
        elif eff == "squash":
            p["squash"] = round(x if rng.random() < 0.5 else 1 / x, 2)
        elif eff == "wobble":
            p.update(wobble=round(x, 3), wobble_freq=round(rng.uniform(1.5, 4.5), 1))
        elif eff == "stretch":
            p["stretch"] = round(x if rng.random() < 0.7 else rng.uniform(0.65, 0.9), 2)
        p["effects"].append(eff)
    if attempt >= 2:
        p = dict(stretch=round(rng.uniform(1.1, 1.5), 2), pivot=p["pivot"], effects=["stretch"])
    return p


# ---------------------------------------------------------------- the weapon
def weapon_type(item_class):
    """A weapon TYPE for variety rules: the item class (shovel/crowbar/lead pipe are all shovels)."""
    return (item_class or "").lower()


def pick_donor(rng, pool, recipe):
    """Donor choice with variety (user: no same weapon type two nights in a row). Hard: no type from
    the previous night's batch or already made tonight (recipe avoid_types). Soft: types used in the
    last nights weigh less (recipe recent_types {type: weight factor}), and a slot already used
    tonight weighs less (recipe taken_slots)."""
    avoid = set(recipe.get("avoid_types") or ())
    cand = [d for d in pool if weapon_type(d["kv"].get("item_class")) not in avoid] or list(pool)
    recent = recipe.get("recent_types") or {}
    slots = set(recipe.get("taken_slots") or ())
    wts = [recent.get(weapon_type(d["kv"].get("item_class")), 1.0) * (0.35 if d["slot"] in slots else 1.0) for d in cand]
    return cand[int(rng.choices(range(len(cand)), weights=wts)[0])]


def choose_classes(ctx, rng, donor, recipe):
    """Classes + item_class for a donor (slot rule + taunt rule); raises when none fits."""
    cfg = ctx.cfg
    fam, slot = donor["fam"], donor["slot"]
    arms_ok = ctx.audit.get("%s:%s" % (donor["src"], donor["id"]), {}).get("arms") or {c: True for c in CLASSES}
    home = [c for c in donor["classes"] if c in CLASSES and arms_ok.get(c, True)] or         [c for c in CLASSES if arms_ok.get(c, True) and slot in CLASS_SLOTS[c]] or ["Soldier"]
    avoid = set(recipe.get("avoid_classes", []))
    classes = {rng.choice([c for c in home if c not in avoid] or home): "1"}
    wrong = None
    if recipe.get("ill_fit") or rng.random() < cfg.get("ill_fit", 0.15):
        c = rng.choice([c for c in CLASSES if c not in home and arms_ok.get(c, True) and
                        (slot in CLASS_SLOTS[c] or fam != "melee")] or home)
        s = slot if slot in CLASS_SLOTS[c] else ("melee" if fam == "melee" else
                                                  next((x for x in ("primary", "secondary") if x in CLASS_SLOTS[c]), None))
        if s:
            classes, wrong = {c: ("1" if s == slot else s)}, c
    if recipe.get("multi") or rng.random() < cfg.get("multi", 0.10):
        extra = [c for c in CLASSES if c not in classes and slot in CLASS_SLOTS[c] and arms_ok.get(c, True)]
        for c2 in rng.sample(extra, min(len(extra), recipe.get("multi_n", 1))):
            classes[c2] = "1"
    # taunts (user: generated weapons must taunt for the classes they're given to): 5205 matches
    # taunt rules on class + the active weapon entity's classname. Use a behaviour-equivalent
    # item_class every chosen class can taunt with (generic shotgun/pistol, the class's own stock
    # melee, or "saxxy" for multi-class melee); if none exists, re-pick a class that can taunt.
    # slot rule (user bug 2026-11-20, slotrule.py): the item_class must natively belong to the slot it
    # is given to for EVERY class, else the client's slot-1/2 keys stop switching. Combined with the
    # taunt rule: slotrule.fix returns an item_class passing both (donor's own, taunt equivalents, or
    # a same-family class native to that slot); else re-pick the class; else re-roll the donor.
    ic0 = donor["kv"].get("item_class")
    eff = lambda cd: {c: slotrule.slot_for(cd, c, slot) for c in cd}          # noqa: E731
    item_class = slotrule.fix(ctx.fs, eff(classes), ic0, fam)
    if item_class is None:
        cands = []
        for c in CLASSES:
            if not arms_ok.get(c, True):
                continue
            s_ = slot if slot in CLASS_SLOTS[c] else ("melee" if fam == "melee" else None)
            if s_ and slotrule.fix(ctx.fs, {c: s_}, ic0, fam):
                cands.append((c, s_))
        pref = [x for x in cands if x[0] in home and x[0] not in avoid] or [x for x in cands if x[0] in home] or cands
        if pref:
            c_, s_ = pref[rng.randrange(len(pref))]
            classes = {c_: "1" if s_ == slot else s_}
            wrong = None if c_ in home else c_
            item_class = slotrule.fix(ctx.fs, eff(classes), ic0, fam)
        else:
            # no class this model fits passes slot + taunt with this weapon: re-roll the donor
            raise RuntimeError("no slot-native, taunt-capable class for %s:%s (%s)" % (donor["src"], donor["id"], ic0))
    slot_ok = {c: slotrule.ok(c, item_class, sl) for c, sl in eff(classes).items()}
    return fam, slot, arms_ok, classes, wrong, item_class, slot_ok


def make_weapon(ctx, defindex, rng, out_dir, recipe=None, used_names=None):
    recipe = recipe or {}
    used_names = used_names if used_names is not None else set()
    cfg = ctx.cfg
    pool = ctx.donors
    if recipe.get("families"):
        pool = [d for d in pool if d["fam"] in recipe["families"]] or pool
    if recipe.get("slot"):
        pool = [d for d in pool if d["slot"] == recipe["slot"]] or pool
    if recipe.get("need_world"):
        pool = [d for d in pool if d["mw"]] or pool
    donor = pick_donor(rng, pool, recipe)
    fam, slot, arms_ok, classes, wrong, item_class, slot_ok = choose_classes(ctx, rng, donor, recipe)
    taunt_ok = {c: taunts.ok(ctx.fs, c, item_class) for c in classes}
    attrs = roll_attributes(ctx, rng, fam, slot, recipe, item_class, list(classes))
    ninfo = dict(item_class=donor["kv"].get("item_class"), fam=fam, slot=slot, classes=list(classes), attrs=attrs, wrong=wrong)
    name = names.make_name(rng, used_names, ninfo)
    traits = [t for t, cond in (("self_ignite", any(a["cls"] == "customslop_ignite_self" for a in attrs)),
                                ("odd_projectile", any(a["cls"] == "custom_projectile_model" for a in attrs)),
                                ("wrong_class", bool(wrong))) if cond]
    projn = next((a["value"].split("/")[-1][:-4].replace("_", " ") for a in attrs if a["cls"] == "custom_projectile_model"), "")
    desc = names.make_description(rng, traits, dict(proj=projn or "something", cls=wrong or "anyone"),
                                  used_names, ninfo, name)
    files = os.path.join(out_dir, "files")
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(files)
    tag = "cs%d" % defindex
    mdir = "models/customslop/" + tag
    matdir = "models/customslop/" + tag
    saved_fs, ctx.fs = ctx.fs, donor["fs"]                 # donor-specific search path (beta/oldmerc files first)
    # ---- colour scheme (region-based, hue-repeat avoidance) and sounds
    assign, hues = palette.scheme(rng, list(ctx.avoid_hues))
    ctx.avoid_hues.extend(hues)
    roles = (["melee_miss", "melee_hit", "melee_hit_world", "deploy"] if fam == "melee" else
             ["deploy", "empty"] if fam == "flame" else ["single_shot", "burst", "reload", "empty", "deploy"])
    snd = {}
    for role in roles:
        pk = ctx.sounds.pick(rng, role)
        if pk:
            snd[role] = pk
    arms_class = next(iter(classes))
    arms_rel = "models/weapons/c_models/c_%s_arms.mdl" % {"Demoman": "demo"}.get(arms_class, arms_class.lower())
    gate, outs = None, {}
    work = tempfile.mkdtemp(prefix="cs_", dir=os.path.join(ROOT, "tmp") if os.path.isdir(os.path.join(ROOT, "tmp")) else None)
    try:
        src_v = extract_model(ctx, donor["mp"], work)
        src_w = extract_model(ctx, donor["mw"], work) if donor["mw"] else None
        orig_img = render_with_fs(ctx, S.load(src_w or src_v), None)
        coarse = MU.is_coarse(S.load(src_w or src_v))
        for attempt in range(3):
            mp = mesh_params(rng, recipe, attempt, coarse=coarse)
            shutil.rmtree(os.path.join(files, "models"), ignore_errors=True)
            shutil.rmtree(os.path.join(files, "materials"), ignore_errors=True)
            outs, reps = {}, {}
            for kind, src in (("v", src_v), ("w", src_w)):
                if src:
                    rel = "%s/%s_%s.mdl" % (mdir, kind, tag)
                    reps[kind] = MU.mutate(src, files, rel, matdir, mp)
                    outs[kind] = os.path.join(files, rel.replace("/", os.sep))
            done = {}
            for kind in ("w", "v"):
                if kind in outs:
                    recolour_regions(ctx, {"v": src_v, "w": src_w}[kind], S.load(outs[kind]), files, matdir, assign, done)
            new_img = render_with_fs(ctx, S.load(outs.get("w") or outs["v"]), files)
            g = dict(attempt=attempt, mesh=mp, coarse=coarse)
            g["structural"] = all(structural_ok(src, outs[k]) for k, src in (("v", src_v), ("w", src_w)) if k in outs)
            g["engine"] = {k: VM.engine_checks(outs[k], files, ctx.fs, src) for k, src in (("v", src_v), ("w", src_w)) if k in outs}
            g["hands"] = {k: VM.hand_checks(src, outs[k]) for k, src in (("v", src_v), ("w", src_w)) if k in outs}
            g["render_gate"], g["detail"] = quality_gate(orig_img, new_img)
            # every texture the shipped models name must have a CustomSlop VMT (else the recolour
            # silently missed it and the weapon would look stock)
            # (textures whose stock material does not exist anywhere - e.g. TF2's unused "black" slot -
            # render identically for everyone and are not counted)
            missing = []
            for k_ in outs:
                mk = S.load(outs[k_])
                for t_ in mk.textures:
                    if os.path.exists(os.path.join(files, "materials", matdir, t_.lower() + ".vmt")):
                        continue
                    if resolve_vmt(ctx, _Cds(mk.cdmaterials[1:]), t_)[1] is not None:
                        missing.append(t_.lower())
            missing = sorted(set(missing))
            g["recolour_complete"] = not missing
            if missing:
                g["recolour_missing"] = missing
            eng_ok = all(ok for k in g["engine"] for ok, _ in g["engine"][k].values())
            hand_ok = all(ok for k in g["hands"] for ok, _ in g["hands"][k].values())
            vm_img, bm = None, None
            if "v" in outs and int(donor["kv"].get("attach_to_hands") or 2) == 2:
                vm_img, bm = VMR.render_viewmodel(ctx, outs["v"], arms_rel, files, size=(640, 360),
                                                  v2=ctx.cfg.get("renderer") == "v2")
                g["arms_bonemerge"] = bm
            bm_ok = bm is None or bm["ok"]
            g["engine_ok"], g["hands_ok"], g["arms_ok"] = eng_ok, hand_ok, bm_ok
            gate = g
            if g["structural"] and eng_ok and hand_ok and bm_ok and g["render_gate"] and g["recolour_complete"]:
                break
        else:
            raise RuntimeError("gates failed after 3 attempts: %s" % {k: gate.get(k) for k in
                               ("structural", "engine_ok", "hands_ok", "arms_ok", "render_gate", "recolour_complete",
                                "recolour_missing", "detail")})
        if ctx.cfg.get("renderer") == "v2":
            # the gates compared v1 renders; the saved previews use the v2 (Source-like) renderer
            orig_img = render_with_fs(ctx, S.load(src_w or src_v), None, v2=True)
            new_img = render_with_fs(ctx, S.load(outs.get("w") or outs["v"]), files, v2=True)
        orig_img.save(os.path.join(out_dir, "render_orig.png"))
        new_img.save(os.path.join(out_dir, "render.png"))
        if vm_img is not None:
            vm_img.save(os.path.join(out_dir, "viewmodel.png"))
        # region debug image for this donor (flat colour per region)
        dbg = region_debug_render(ctx, src_w or src_v)
        if dbg is not None:
            dbg.save(os.path.join(out_dir, "regions_debug.png"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        ctx.fs = saved_fs
    # icon in the donor's own stock-icon style (fitted camera + lighting, cached per donor)
    icon, gate["icon_style"] = styled_icon(ctx, donor, fam, outs, files, new_img)
    icon.save(os.path.join(out_dir, "icon.png"))
    ip = os.path.join(files, "materials", "backpack", "customslop", tag + "_large.vtf")
    os.makedirs(os.path.dirname(ip), exist_ok=True)
    if ctx.cfg.get("renderer") == "v2":
        # crisp edges in game: premultiplied area resize, edge colour bled into transparent texels
        # (no black fringe under bilinear filtering), premultiplied mips, uncompressed BGRA8888
        import srcshade as SS_
        rs = lambda im_, sz: SS_.bleed_edges(SS_.resize_premul(im_, sz))       # noqa: E731
        small = rs(np.asarray(icon.convert("RGBA")), (ICON_SIZE, ICON_SIZE))
        open(ip, "wb").write(vtf.encode(small, fmt=12, mips=True, resample=rs))
    else:
        small = icon.convert("RGBA").resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
        open(ip, "wb").write(vtf.encode(np.asarray(small), fmt=15, mips=True))
    open(ip[:-4] + ".vmt", "w").write('"UnlitGeneric"\n{\n\t"$baseTexture" "backpack/customslop/%s_large"\n'
                                      '\t"$translucent" 1\n\t"$vertexcolor" 1\n\t"$ignorez" 1\n}\n' % tag)
    ok_icon, why_icon = VM.vtf_check(open(ip, "rb").read())
    gate["icon_vtf"] = (ok_icon, why_icon)
    # ---- size cap (everything a client downloads for this weapon, bz2 as FastDL serves it)
    import bz2
    import hashlib
    manifest = []
    for dp, _, fs_ in os.walk(files):
        for f in fs_:
            p_ = os.path.join(dp, f)
            raw_ = open(p_, "rb").read()
            manifest.append(dict(path=os.path.relpath(p_, files).replace("\\", "/"), bytes=len(raw_),
                                 bz2=len(bz2.compress(raw_, 9)), sha1=hashlib.sha1(raw_).hexdigest()))
    bz_total = sum(x["bz2"] for x in manifest)
    gate["size"] = dict(raw=sum(x["bytes"] for x in manifest), bz2=bz_total, cap=SIZE_CAP_BZ2, ok=bz_total <= SIZE_CAP_BZ2)
    if not gate["size"]["ok"] or not ok_icon:
        raise RuntimeError("size cap / icon gate failed: %s %s" % (gate["size"], why_icon))
    # ---- sounds (customslop.<id>.<role> soundscripts; waves are stock content clients already have)
    sscript = "".join(sounds_mod.soundscript("customslop.%d.%s" % (defindex, r_), pk, r_) for r_, pk in snd.items())
    open(os.path.join(out_dir, "sounds.txt"), "w", encoding="utf-8").write(sscript)
    # ---- card
    lines = attrdesc.sort_lines(attrdesc.item_lines([(a["name"], a["value"]) for a in attrs], ctx.defs, ctx.L))
    lines.append((desc, "neutral"))
    # item_type_name: a token TF2C itself localises for this item class (labels.py), else a literal
    ic_ = donor["kv"].get("item_class", "")
    # the DONOR's own weapon name (user: "Hammerfists", "Assault Rifle", "Lead Pipe"), else the class token
    itn = labels.donor_type_name(donor["src"], donor["kv"], ctx.tf2c_tokens) or         labels.type_token(ic_, slot, donor["src"], donor["kv"].get("item_type_name"), ctx.tf2c_tokens, ctx.stock_types)
    if itn and not itn.startswith("#"):
        typ = itn
    elif itn:
        typ = ctx.tf2c_tokens[itn[1:].lower()]
    else:
        typ = TYPE_NAMES.get(ic_, re.sub(r"^tf2?c?_weapon_", "", ic_).replace("_", " ").title())
        itn = typ
    level = rng.randint(1, 100)
    type_line = ctx.L.get("#ItemTypeDesc").replace("%s1", str(level)).replace("%s2", typ)
    cimg = card.render_card(name, type_line, lines, icon, fonts=ctx.fonts, crisp=ctx.cfg.get("renderer") == "v2")
    cimg.save(os.path.join(out_dir, "card.png"))
    # ---- schema fragment
    it = emit(defindex, name, desc, donor, slot, classes, attrs, mdir, tag, outs, snd, itn=itn, item_class=item_class)
    frag = '"%d"\n{\n%s}\n' % (defindex, kv.dump(it, 1))
    own = {n.lower(): dict(integer=False) for n in ctx.attr_registry}
    own["customslop ignite self on attack"] = dict(integer=False)
    serrs = VM.schema_check(frag, ctx.schema_defs, own, ctx.item_classes)
    gate["schema"] = serrs or "ok"
    if serrs:
        raise RuntimeError("schema gate failed (5205 would reject the whole schema): %s" % serrs[:3])
    lerrs = labels.label_check(frag, ctx.tf2c_tokens)
    gate["labels"] = lerrs or "ok"
    if lerrs:
        raise RuntimeError("label gate failed: %s" % lerrs[:3])
    open(os.path.join(out_dir, "item.txt"), "w", encoding="utf-8").write(frag)
    summary = dict(defindex=defindex, name=name, description=desc, classes=classes, wrong_class=wrong, slot=slot,
                   item_class=item_class, taunt=taunt_ok, slot_native=slot_ok,
                   family=fam, level=level, type_line=type_line,
                   base=dict(src=donor["src"], id=donor["id"], item_class=donor["kv"].get("item_class"),
                             model_player=donor["mp"], model_world=donor["mw"], credit=donor["credit"]),
                   attributes=[dict(a, line=(attrdesc.line(ctx.defs.get(a["name"].lower(), {}), a["value"], ctx.L) or [None])[0])
                               for a in attrs],
                   card_lines=lines, colours=dict(assign=assign, hues=[round(h) for h in hues]),
                   sounds=snd, gate=gate, recipe=recipe, assets=manifest,
                   asset_bytes=sum(m_["bytes"] for m_ in manifest), asset_bz2=bz_total)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=1, default=str)
    return summary


def styled_icon(ctx, donor, fam, outs, files, fallback_img):
    """Render the mutated world model (else view model) with the camera + lighting fitted to the
    donor's stock icon (iconfit.py; fitted on first use and cached). Donors without a stock icon:
    default camera with the family's mean fitted lighting; nothing fitted at all: the plain render."""
    import random as _r
    import fit_icons
    key = "%s:%s" % (donor["src"], donor["id"])
    v2 = ctx.cfg.get("renderer") == "v2"
    fver = int(ctx.cfg.get("icon_fit_version", 2)) if v2 else 1      # camera fit cache version (v3: audited)
    cp = IF.cache_path(key, fver)
    f = json.load(open(cp)) if os.path.exists(cp) else None
    saved, ctx.fs = ctx.fs, donor["fs"]
    try:
        if f is None:
            if v2:
                try:
                    _, f, _ = fit_icons.fit_donor_v2(ctx, donor, _r.Random(7), version=fver)
                except Exception:              # a failed camera fit must never fail the weapon
                    f = None
            elif fit_icons.stock_icon(ctx, donor) is not None:
                _, f, _ = fit_icons.fit_donor(ctx, donor, _r.Random(7))
        use_v = v2 and (f or {}).get("model_kind") == "v" and outs.get("v")
        m = S.load(outs["v"] if use_v else (outs.get("w") or outs["v"]))
        if v2 and (use_v or not outs.get("w")):
            m = IF.posed(m)                     # a v_ model is only assembled in its idle pose
        tex = VMR.textures_for(ctx, m, files)
        mats = VMR.materials_for(ctx, m, files) if v2 else None
    finally:
        ctx.fs = saved
    if f and v2 and f["scores"].get("iou_canvas", 1) < (0.6 if fver < 3 else 0.4):
        # the icon could not be matched (e.g. a nearest same-weapon icon of a different model):
        # a clean side-on default camera beats a forced, odd pose
        return IF.render_icon(m, tex, IF.default_style(m), mats=mats), dict(
            style="default side-on camera (best icon fit IoU %.2f < 0.6: %s)" % (f["scores"]["iou_canvas"], f.get("icon_src")),
            renderer="v2")
    if f:
        return IF.render_icon(m, tex, f, mats=mats, legacy=not v2), dict(
            style="fitted to the donor's own icon (%s)" % (f.get("icon_src") or "stock"), renderer="v2" if v2 else "v1",
            scores=f["scores"])
    fs_ = IF.family_style(fam)
    st_ = IF.default_style(m, fs_["light"] if fs_ else None)
    return IF.render_icon(m, tex, st_, mats=mats, legacy=not v2), dict(style="default camera + %s" % (
        "mean fitted lighting of the %s family" % fam if fs_ else "default lighting"), renderer="v2" if v2 else "v1")


def recolour_regions(ctx, src_path, model, files, matdir, assign, done):
    """Recolour every base texture the model uses, region by region (regions.py), into matdir."""
    src_model = S.load(src_path)
    sizes, metas = {}, {}
    for k, tex in enumerate(model.textures):
        rel, t = resolve_vmt(ctx, model, tex)
        if not t:
            continue
        mm = re.search(r'"\$basetexture"\s+"([^"]+)"', t, re.I)
        if not mm:
            continue
        bt = mm.group(1).replace("\\", "/").lower()
        raw = ctx.fs.read("materials/" + bt + ".vtf")
        if raw is None:
            continue
        w, h, img, info = vtf.decode(raw)
        if max(w, h) > TEX_MAX:
            kk = TEX_MAX / max(w, h)
            img = np.asarray(Image.fromarray(img, "RGBA").resize((max(4, int(w * kk)), max(4, int(h * kk))), Image.LANCZOS))
        sizes[k] = (img.shape[1], img.shape[0])
        metas[k] = (tex, t, bt, img, info)
    maps, _ = REG.region_map(src_path, src_model, sizes)
    for k, (tex, t, bt, img, info) in metas.items():
        if bt not in done:
            rgb = img[..., :3].astype(np.float32) / 255
            out = rgb.copy()
            if k in maps:
                masks, station = maps[k]
                covered = np.clip(masks.sum(0), 0, 1)
                acc = np.zeros_like(rgb)
                for r_, nm in enumerate(REG.NAMES):
                    acc += palette.apply_op(rgb, assign[nm], station) * masks[r_][..., None]
                out = acc + palette.apply_op(rgb, assign["body"], station) * (1 - covered)[..., None]
            else:
                out = palette.apply_op(rgb, assign["body"])
            res = np.dstack([(np.clip(out, 0, 1) * 255 + .5).astype(np.uint8), img[..., 3]])
            name = "%s_%d" % (os.path.basename(bt), len(done))
            dst = os.path.join(files, "materials", matdir, name + ".vtf")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            fmt = 13 if res[..., 3].min() >= 250 else 15
            open(dst, "wb").write(vtf.encode(res, fmt=fmt, mips=True, flags=info["flags"] & ~0x4000))
            done[bt] = matdir + "/" + name
        t2 = re.sub(r'("\$basetexture"\s+)"[^"]*"', lambda m_: m_.group(1) + '"%s"' % done[bt], t, flags=re.I)
        vp = os.path.join(files, "materials", matdir, tex.lower() + ".vmt")
        os.makedirs(os.path.dirname(vp), exist_ok=True)
        open(vp, "w", encoding="latin-1").write(t2)


def region_debug_render(ctx, src_path):
    """Render the donor with each colour region as a flat colour (validates the region map)."""
    m = S.load(src_path)
    sizes = {}
    for k, tex in enumerate(m.textures):
        sizes[k] = (TEX_MAX, TEX_MAX)
    try:
        maps, _ = REG.region_map(src_path, m, sizes)
    except Exception:
        return None
    texs = {k: REG.debug_texture(v[0]) for k, v in maps.items()}
    return RD.render(m, [], size=384, ss=1, textures=texs)


def struct_wh(raw):
    import struct
    return struct.unpack_from("<HH", raw, 16)


def structural_ok(orig, new):
    import build_proto
    r = build_proto.validate(orig, new)
    return all(r[k] for k in ("checksums_agree", "checksum_unchanged", "length_field_matches_file", "vertex_count_same",
                              "tris_identical", "max_tri_index_ok", "finite", "hull_contains_verts", "bones_identical",
                              "vtx_bytes_identical"))


def render_with_fs(ctx, model, files_root, v2=False):
    """Render resolving textures through files_root first (new materials), then the game VFS."""
    tex = {}
    for k, tname in enumerate(model.textures):
        img = None
        for cd in model.cdmaterials:
            relv = "materials/" + re.sub("/+", "/", (cd + tname).replace(chr(92), "/")).lstrip("/").lower() + ".vmt"
            t = None
            if files_root and os.path.exists(os.path.join(files_root, relv)):
                t = open(os.path.join(files_root, relv), encoding="latin-1").read()
            elif ctx.fs.read(relv) is not None:
                _, t = resolve_vmt(ctx, _One(cd), tname)
            if t:
                mm = re.search(r'"\$basetexture"\s+"([^"]+)"', t, re.I)
                if mm:
                    bt = "materials/" + mm.group(1).replace("\\", "/").lower() + ".vtf"
                    raw = open(os.path.join(files_root, bt), "rb").read() if files_root and os.path.exists(os.path.join(files_root, bt)) \
                        else ctx.fs.read(bt)
                    if raw:
                        img = vtf.decode(raw)[2]
                break
        tex[k] = img
    if v2:
        return RD.render(model, [], size=512, ss=4, textures=tex, mats=VMR.materials_for(ctx, model, files_root), v2=True)
    return RD.render(model, [], size=512, ss=2, textures=tex)


class _Cds:
    def __init__(self, cds):
        self.cdmaterials = list(cds)


class _One:
    def __init__(self, cd):
        self.cdmaterials = [cd]


def emit(defindex, name, desc, donor, slot, classes, attrs, mdir, tag, outs, snd=None, itn=None, item_class=None):
    # never carry Merc / tf2cc-only keys onto a non-Merc item (labels.sanitize)
    d = labels.sanitize(donor["kv"], donor["src"], list(classes))
    it = kv.KV()
    for k_, v_ in (("name", "customslop_%d" % defindex), ("item_name", name),
                   ("item_type_name", itn), ("item_description", desc),
                   ("item_quality", "unique"), ("propername", "0"), ("item_class", item_class or d.get("item_class")),
                   ("item_slot", slot)):
        it.add(k_, v_)
    ubc = kv.KV()
    for c, s in classes.items():
        ubc.add(c, s)
    it.add("used_by_classes", ubc)
    for key in ("anim_slot", "attach_to_hands", "flip_viewmodel", "bucket", "item_logname", "item_iconname",
                "mouse_pressed_sound", "drop_sound", "extra_wearable"):
        if d.get(key) is not None:
            it.add(key, d.get(key))
    it.add("model_player", "%s/v_%s.mdl" % (mdir, tag) if "v" in outs else d.get("model_player"))
    if "w" in outs:
        it.add("model_world", "%s/w_%s.mdl" % (mdir, tag))
    it.add("image_inventory", "backpack/customslop/%s" % tag)
    for key in ("static_attrs", "visuals_red", "visuals_blu", "visuals_grn", "visuals_ylw"):
        if isinstance(d.get(key), kv.KV):
            it.add(key, d.get(key))
    # visuals: the donor's (animation replacements etc.) with CustomSlop's random sound scripts on top
    vis = kv.KV()
    if isinstance(d.get("visuals"), kv.KV):
        vis.pairs = [(k_, v_) for k_, v_ in d.get("visuals").pairs
                     if not (snd and k_.lower().startswith("sound_") and k_.lower()[6:] in snd)]
    for role in (snd or {}):
        vis.add("sound_" + role, "customslop.%d.%s" % (defindex, role))
    if vis.pairs:
        it.add("visuals", vis)
    a = kv.KV()
    for x in attrs:
        b = kv.KV()
        b.add("attribute_class", x["cls"])
        b.add("value", str(x["value"]))
        a.add(x["name"], b)
    it.add("attributes", a)
    tags = kv.KV()
    tags.add("customslop", "1")
    it.add("tags", tags)
    return it
