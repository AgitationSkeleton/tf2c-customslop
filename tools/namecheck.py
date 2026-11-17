"""Prove CustomSlop name/description diversity: roll N names + descriptions with fresh state for several
seeds across all classes / item classes and report max pairwise similarity, template spread, repeats
and guard-stage use. Pure (no files read or written).

  python -B namecheck.py [--seeds 1 2 3 4 5] [--sample 50] [--big 500] [--show 50]
"""
import argparse
import itertools
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import names as N  # noqa: E402

ITEM_CLASSES = [("tf_weapon_rocketlauncher", "rocket", "primary"), ("tf_weapon_grenadelauncher", "grenade", "primary"),
                ("tf_weapon_pipebomblauncher", "grenade", "secondary"), ("tf_weapon_minigun", "hitscan", "primary"),
                ("tf_weapon_flamethrower", "flame", "primary"), ("tf_weapon_flaregun", "projectile", "secondary"),
                ("tf_weapon_scattergun", "hitscan", "primary"), ("tf_weapon_shotgun", "hitscan", "secondary"),
                ("tf_weapon_pistol", "hitscan", "secondary"), ("tf_weapon_revolver", "hitscan", "primary"),
                ("tf_weapon_smg", "hitscan", "secondary"), ("tf_weapon_syringegun_medic", "projectile", "primary"),
                ("tf_weapon_nailgun", "projectile", "primary"), ("tf_weapon_sniperrifle", "hitscan", "primary"),
                ("tf_weapon_compound_bow", "projectile", "primary"), ("tf_weapon_bat", "melee", "melee"),
                ("tf_weapon_shovel", "melee", "melee"), ("tf_weapon_wrench", "melee", "melee"),
                ("tf_weapon_bonesaw", "melee", "melee"), ("tf_weapon_knife", "melee", "melee"),
                ("tf_weapon_fireaxe", "melee", "melee"), ("tf_weapon_bottle", "melee", "melee"),
                ("tf_weapon_club", "melee", "melee"), ("tf_weapon_fists", "melee", "melee"),
                ("tf_weapon_umbrella", "melee", "melee")]
ATTRS = ["mult_dmg", "mult_postfiredelay", "mult_clipsize", "mult_reload_time", "mult_maxammo_primary",
         "set_dmgtype_ignite", "mult_wpn_burndmg", "mult_explosion_radius", "mult_crit_chance", "mult_player_movespeed",
         "add_onhit_addhealth", "mult_dmgtaken_from_fire", "mult_spread_scale", "add_buildings_upgrade_cost",
         "mult_cloak_meter_regen", "headshot_damage_modify", "mult_flame_life", "mult_knockback", "mult_deploy_time"]
CLASSES = N.NW.CLASSES_ALL


def roll_info(r):
    ic, fam, slot = r.choice(ITEM_CLASSES)
    attrs = [dict(cls=c, value=round(r.choice([r.uniform(0.4, 0.9), r.uniform(1.1, 2.0), 1, 25]), 2))
             for c in r.sample(ATTRS, r.randint(3, 7))]
    wrong = r.choice(CLASSES) if r.random() < 0.15 else None
    traits = [t for t, p in (("self_ignite", 0.08), ("odd_projectile", 0.1 if fam in ("rocket", "grenade") else 0),
                             ("wrong_class", 1 if wrong else 0)) if r.random() < p]
    return dict(item_class=ic, fam=fam, slot=slot, classes=[r.choice(CLASSES)], attrs=attrs, wrong=wrong), traits


def roll(seed, n):
    r = random.Random(seed)
    h = N.History()
    out = []
    for _ in range(n):
        info, traits = roll_info(r)
        nm = N.make_name(r, h, info)
        d = N.make_description(r, traits, dict(proj="a rubber chicken", cls=info["wrong"] or "anyone"), h, info, nm)
        out.append((nm, d, info))
    return h, out


def pair_stats(h, lo, hi):
    """Max pairwise similarity metrics among names/descs [lo:hi) and count of guard-'similar' pairs."""
    ns, ds = h.names[lo:hi], h.descs[lo:hi]
    m = Counter()
    worst = {}
    for a, b in itertools.combinations(range(len(ns)), 2):
        A, B = ns[a], ns[b]
        for k, v in (("name_tok_jaccard", N.jaccard(A["toks"], B["toks"])), ("name_tri_jaccard", N.jaccard(A["tri"], B["tri"])),
                     ("name_shared_stems", len(A["stems"] & B["stems"]))):
            if v > m[k]:
                m[k], worst[k] = v, (A["name"], B["name"])
        m["name_similar_pairs"] += N.name_similar(dict(A, tid=None), B)
        m["name_same_template_head"] += bool(A["tid"] and A["tid"] == B["tid"] and A["head"] == B["head"])
        C, D = ds[a], ds[b]
        for k, v in (("desc_stem_jaccard", N.jaccard(C["stems"], D["stems"])), ("desc_tri_jaccard", N.jaccard(C["tri"], D["tri"])),
                     ("desc_shared_fragments", len(C["frags"] & D["frags"])), ("desc_shared_4word", len(C["sh"] & D["sh"]))):
            if v > m[k]:
                m[k], worst[k] = v, (C["text"], D["text"])
        m["desc_similar_pairs"] += N.desc_similar(C, D)
    return m, worst


def windows(h, n, w=50):
    agg = Counter()
    for lo in range(0, max(1, n - w + 1), 10):
        m, _ = pair_stats(h, lo, lo + w)
        m["max_template_in_window"] = max(Counter(x["tid"] for x in h.names[lo:lo + w]).values())
        m["max_form_in_window"] = max(Counter(x["form"] for x in h.descs[lo:lo + w]).values())
        for k, v in m.items():
            agg[k] = max(agg[k], v) if not k.endswith("pairs") and not k.endswith("head") else agg[k] + v
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3, 4, 5, 20261117])
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--big", type=int, default=500)
    ap.add_argument("--show", type=int, default=50)
    a = ap.parse_args()
    fails = 0
    print("name space ~%.2e names; %d name templates; %d description forms" % (
        N.combinations(), len(N.NAME_TEMPLATES), len(N.DESC_FORMS)))
    for seed in a.seeds:
        N.STATS.clear()
        h, out = roll(seed, a.sample)
        m, worst = pair_stats(h, 0, a.sample)
        tpl = Counter(x["tid"] for x in h.names)
        frm = Counter(x["form"] for x in h.descs)
        lens = [len(d["text"]) for d in h.descs]
        bad = m["name_similar_pairs"] + m["desc_similar_pairs"] + m["name_same_template_head"]
        fails += bad
        print("\n=== seed %s: %d rolls ===" % (seed, a.sample))
        print("  names: max token-Jaccard %.2f  max trigram-Jaccard %.2f  max shared word-stems %d  similar pairs %d  same template+head %d" % (
            m["name_tok_jaccard"], m["name_tri_jaccard"], m["name_shared_stems"], m["name_similar_pairs"], m["name_same_template_head"]))
        print("         worst trigram pair: %s | %s" % worst.get("name_tri_jaccard", ("-", "-")))
        print("  descs: max stem-Jaccard %.2f  max trigram-Jaccard %.2f  shared fragments %d  shared 4-word runs %d  similar pairs %d" % (
            m["desc_stem_jaccard"], m["desc_tri_jaccard"], m["desc_shared_fragments"], m["desc_shared_4word"], m["desc_similar_pairs"]))
        print("  templates used %d/%d, max share %d/%d (%s); forms used %d/%d, max share %d (%s)" % (
            len(tpl), len(N.NAME_TEMPLATES), max(tpl.values()), a.sample, tpl.most_common(1)[0][0],
            len(frm), len(N.DESC_FORMS), max(frm.values()), frm.most_common(1)[0][0]))
        print("  desc length min/avg/max %d/%d/%d chars; exact repeats: names %d descs %d; guard stages %s" % (
            min(lens), sum(lens) // len(lens), max(lens), a.sample - len({x["name"].lower() for x in h.names}),
            a.sample - len({x["norm"] for x in h.descs}), dict(N.STATS)))
        if seed == a.seeds[0] and a.show:
            print("\n  --- %d-roll sample (seed %s) ---" % (a.show, seed))
            for i, (nm, d, info) in enumerate(out[:a.show], 1):
                print("  %2d. %-40s [%s, %s]\n      %s" % (i, nm, info["classes"][0], info["item_class"][10:], d))
    if a.big:
        for seed in a.seeds[:3]:
            N.STATS.clear()
            h, out = roll(seed, a.big)
            agg = windows(h, a.big)
            tpl = Counter(x["tid"] for x in h.names)
            frm = Counter(x["form"] for x in h.descs)
            rep_n = a.big - len({x["name"].lower() for x in h.names})
            rep_d = a.big - len({x["norm"] for x in h.descs})
            bad = agg["name_similar_pairs"] + agg["desc_similar_pairs"] + agg["name_same_template_head"]
            fails += bad + rep_n + rep_d
            print("\n=== seed %s: %d rolls (every 50-roll window, step 10) ===" % (seed, a.big))
            print("  names: max token-Jaccard %.2f trigram %.2f shared stems %d; similar pairs in any window %d; same template+head %d" % (
                agg["name_tok_jaccard"], agg["name_tri_jaccard"], agg["name_shared_stems"], agg["name_similar_pairs"],
                agg["name_same_template_head"]))
            print("  descs: max stem-Jaccard %.2f trigram %.2f shared fragments %d shared 4-word %d; similar pairs %d" % (
                agg["desc_stem_jaccard"], agg["desc_tri_jaccard"], agg["desc_shared_fragments"], agg["desc_shared_4word"],
                agg["desc_similar_pairs"]))
            print("  most uses of one name template in any 50 window: %d; of one description form: %d" % (
                agg["max_template_in_window"], agg["max_form_in_window"]))
            print("  exact repeats over all %d: names %d descs %d; templates %d/%d (max share %.1f%%), forms %d/%d (max %.1f%%); stages %s" % (
                a.big, rep_n, rep_d, len(tpl), len(N.NAME_TEMPLATES), 100.0 * max(tpl.values()) / a.big,
                len(frm), len(N.DESC_FORMS), 100.0 * max(frm.values()) / a.big, dict(N.STATS)))
    print("\nRESULT:", "PASS" if fails == 0 else "FAIL (%d)" % fails)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
