"""Recreate the user's three reference cards (Sandman, Scorch Shot, Tribalman's Shiv) from TF2's
own schema + localisation + backpack icons, through the same card/attrdesc code CustomSlop uses,
and put each next to the reference for comparison. Output: cards/ref_*.png, cards/ref_compare_*.png
"""
import io
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths as P  # noqa: E402
import attrdesc  # noqa: E402
import card  # noqa: E402
import kv  # noqa: E402
import loc  # noqa: E402
import vfs  # noqa: E402
import vtf  # noqa: E402

REFS = P.opt("card_reference_dir") or os.path.join(ROOT, "cards", "references")   # 1.png 2.png 3.png
TF2_SCHEMA = os.path.join(P.cfg("tf2_server_dir"), "tf", "scripts", "items", "items_game.txt")
TF2_ONLY = [("vpk", os.path.join(vfs.TF2_CLIENT, "tf", "tf2_textures_dir.vpk")), ("vpk", os.path.join(vfs.TF2, "tf", "tf2_misc_dir.vpk"))]


P, N, C = "positive", "negative", "neutral"
EXACT = {  # the reference screenshots' literal text (they come from a newer/live TF2 build)
    "44": ("The Sandman", "Level 15 Bat", [
        ('Alt-Fire: Launches a ball that deals 40 Damage and "marks" opponents for 5 seconds', P),
        ("Marked opponents will take guaranteed Critical Damage from throwing weapons", P),
        ("-15 max health on wearer", N)]),
    "740": ("The Scorch Shot", "Level 10 Flare Gun", [
        ("100% mini-crits vs burning players", P),
        ("Flare knocks back target on hit and explodes when it hits the ground", P),
        ("Increased knockback on burning players", P),
        ("Increased knockback on players launched airborne by explosions, grapple hooks or rocket packs (stacks with above)", P),
        ("-35% self damage force", N), ("-65% damage penalty for the hit", N), ("Mini-crits are affected by range", N),
        ("No random crits", N), ("Afterburn is not affected by mini-crits", N),
        ("This weapon will reload automatically when not active.", C)]),
    "171": ("The Tribalman's Shiv", "Level 5 Kukri", [
        ("On Hit: Bleed for 6 seconds", P), ("on hit gain a 3-speed boost (as fast as a spy)", P),
        ("-50% damage penalty", N), ("no random crits", N)]),
}


def resolved(items, prefabs, it):
    out, attrs = {}, []
    for p in (it.get("prefab") or "").split():
        pk = prefabs.get(p)
        if pk is not None:
            o, a = resolved(items, prefabs, pk)
            out.update(o)
            attrs += a
    for k, v in it.pairs:
        if k.lower() == "attributes" and isinstance(v, kv.KV):
            attrs += [(n, b.get("value")) for n, b in v.blocks()]
        else:
            out[k.lower()] = v
    return out, attrs


def main():
    ig = kv.load(TF2_SCHEMA)[0].get("items_game")
    items, prefabs = ig.get("items"), ig.get("prefabs")
    defs = attrdesc.defs_from_schema(ig)
    L = loc.Loc(loc.CANDIDATES[:2])        # TF2's own strings only, like the reference screenshots
    fs = vfs.VFS(TF2_ONLY)
    fonts = card.find_fonts()
    os.makedirs(os.path.join(ROOT, "cards"), exist_ok=True)
    for idx, (iid, lvl, ref) in enumerate([("44", 15, "1.png"), ("740", 10, "2.png"), ("171", 5, "3.png")]):
        d, attrs = resolved(items, prefabs, items.get(iid))
        name = L.get(d.get("item_name"), d.get("name"))
        name = name if not name.startswith("#") else d.get("name")
        typ = L.get(d.get("item_type_name"), "")
        lines = attrdesc.sort_lines(attrdesc.item_lines(attrs, defs, L))
        if d.get("item_description"):
            lines.append((L.get(d["item_description"]), "neutral"))
        icon = None
        img = d.get("image_inventory")
        if img:
            raw = fs.read("materials/" + img + "_large.vtf") or fs.read("materials/" + img + ".vtf")
            if raw:
                icon = Image.fromarray(vtf.decode(raw)[2], "RGBA")
        if d.get("propername") == "1" and not name.lower().startswith("the "):
            name = "The " + name
        c = card.render_card(name,
                             L.get("#ItemTypeDesc").replace("%s1", str(lvl)).replace("%s2", typ), lines, icon, fonts=fonts)
        c.save(os.path.join(ROOT, "cards", "ref_%s.png" % iid))
        r = Image.open(os.path.join(REFS, ref)).convert("RGBA")
        r = r.resize((c.width, int(r.height * c.width / r.width)))
        sh = Image.new("RGBA", (c.width * 2 + 20, max(c.height, r.height)), (255, 255, 255, 255))
        sh.alpha_composite(r, (0, 0))
        sh.alpha_composite(c, (c.width + 20, 0))
        sh.save(os.path.join(ROOT, "cards", "ref_compare_%s.png" % iid))
        ex = card.render_card(EXACT[iid][0], EXACT[iid][1], EXACT[iid][2], icon, fonts=fonts)
        ex.save(os.path.join(ROOT, "cards", "ref_exact_%s.png" % iid))
        sh = Image.new("RGBA", (c.width * 3 + 40, max(c.height, r.height, ex.height)), (255, 255, 255, 255))
        sh.alpha_composite(r, (0, 0))
        sh.alpha_composite(ex, (c.width + 20, 0))
        sh.alpha_composite(c, (2 * c.width + 40, 0))
        sh.save(os.path.join(ROOT, "cards", "ref_compare_%s.png" % iid))
        print(iid, name, "|", [l for l in lines])


if __name__ == "__main__":
    main()
