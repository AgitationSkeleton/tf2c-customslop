"""Re-render live CustomSlop weapons' icons with their donor's CURRENT camera, shipped under a NEW
versioned path (clients never re-download an existing FastDL path):
  materials/backpack/customslop/cs<id>_v<n>_large.vtf/.vmt, image_inventory backpack/customslop/cs<id>_v<n>
The weapon's catalogue entry gets the new files appended to its assets (the old icon files stay
catalogued until the weapon retires - own-files rule), icon_version, and icon_pending (the apply
step keeps the previous fragment until the new files are verified on FastDL). Backups:
item.txt.pre_reicon, icon.png.pre_v<n>, card.png.pre_v<n>. Journal: "reicon".
A weapon is re-rendered only when its donor camera differs from the one its current icon used
(fit scores differ), unless --force.

  python -I reicon.py [--ids ...] [--force] [--dry-run]
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import iconfit as IF  # noqa: E402
import pipeline as P  # noqa: E402  (puts kv on the path)
import kv  # noqa: E402
import slopqueue as Q  # noqa: E402
import srcshade as SS  # noqa: E402
import vtf  # noqa: E402


def camera_changed(summ, f):
    used = ((summ.get("gate") or {}).get("icon_style") or {})
    if used.get("renderer") != "v2":
        return True, "icon made with renderer %s" % used.get("renderer")
    if not f:
        return False, "no current camera"
    if (used.get("scores") or {}) != (f.get("scores") or {}):
        return True, "camera changed (%s -> %s)" % ((used.get("scores") or {}).get("iou_canvas"), f["scores"].get("iou_canvas"))
    return False, "same camera"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = Q.cfg()
    st = Q.load_state(c)
    c2 = dict(c)
    c2["_attr_registry"], c2["_used_hues"] = c.get("_attr_registry", {}), []
    ctx = P.Ctx(c2)
    fver = int(c.get("icon_fit_version", 2))
    done = []
    for k, w in sorted(st["weapons"].items()):
        if w["status"] not in ("live", "approved") or (a.ids and int(k) not in a.ids):
            continue
        d = os.path.join(ROOT, w["dir"])
        summ = json.load(open(os.path.join(d, "summary.json")))
        b = summ["base"]
        donor = next((x for x in ctx.donors if x["src"] == b["src"] and x["id"] == b["id"]), None)
        if donor is None:
            print(k, "donor not in roster - skipped")
            continue
        key = "%s:%s" % (donor["src"], donor["id"])
        cp = IF.cache_path(key, fver)
        f = json.load(open(cp)) if os.path.exists(cp) else None
        ch, why = camera_changed(summ, f)
        if not (ch or a.force):
            print(k, "kept:", why)
            continue
        n = int(w.get("icon_version", 1)) + 1
        tag = "cs%s_v%d" % (k, n)
        files = os.path.join(d, "files")
        mdir = os.path.join(files, "models", "customslop", "cs%s" % k)
        outs = {kk: os.path.join(mdir, "%s_cs%s.mdl" % (kk, k)) for kk in ("w", "v")}
        outs = {kk: v for kk, v in outs.items() if os.path.exists(v)}
        print(k, "re-render:", why, "->", tag)
        if a.dry_run:
            done.append(int(k))
            continue
        icon, style = P.styled_icon(ctx, donor, summ.get("family") or donor["fam"], outs, files, None)
        rel_vtf = "materials/backpack/customslop/%s_large.vtf" % tag
        rel_vmt = "materials/backpack/customslop/%s_large.vmt" % tag
        ip = os.path.join(files, rel_vtf)
        os.makedirs(os.path.dirname(ip), exist_ok=True)
        rs = lambda im_, sz: SS.bleed_edges(SS.resize_premul(im_, sz))       # noqa: E731
        small = rs(np.asarray(icon.convert("RGBA")), (P.ICON_SIZE, P.ICON_SIZE))
        open(ip, "wb").write(vtf.encode(small, fmt=getattr(P, "ICON_VTF_FMT", 12), mips=True, resample=rs))
        open(os.path.join(files, rel_vmt), "w").write('"UnlitGeneric"\n{\n\t"$baseTexture" "backpack/customslop/%s_large"\n'
                                                      '\t"$translucent" 1\n\t"$vertexcolor" 1\n\t"$ignorez" 1\n}\n' % tag)
        ok_icon, why_icon = P.VM.vtf_check(open(ip, "rb").read())
        if not ok_icon:
            raise SystemExit("%s: icon VTF check failed: %s" % (k, why_icon))
        for fn in ("icon.png", "card.png"):
            src = os.path.join(d, fn)
            if os.path.exists(src) and not os.path.exists(src + ".pre_v%d" % n):
                shutil.copyfile(src, src + ".pre_v%d" % n)
        icon.save(os.path.join(d, "icon.png"))
        ipath = os.path.join(d, "item.txt")
        # .pre_reicon = the fragment the server keeps until the NEW icon files are verified on
        # FastDL (apply.item_text). It must be the currently-live fragment: refresh it when the
        # previous re-render's files are already published (else the server would fall back to an
        # older icon AND older keys); keep it while a previous re-render is still unpublished.
        prev = ipath + ".pre_reicon"
        pub = {r_["path"] for r_ in w.get("published_blobs", [])}
        prev_unpub = [p_ for p_ in (w.get("icon_pending") or [])
                      if not any(x == p_ + ".bz2" or x.endswith("/" + p_ + ".bz2") for x in pub)]
        if not os.path.exists(prev) or not prev_unpub:
            if os.path.exists(prev):
                shutil.copyfile(prev, prev + ".v%d" % (n - 1))
            shutil.copyfile(ipath, prev)
        key_, it = kv.parse(open(ipath, encoding="utf-8").read())[0].pairs[0]
        it = kv.KV([(kk, "backpack/customslop/%s" % tag if kk.lower() == "image_inventory" else v) for kk, v in it.pairs])
        open(ipath, "w", encoding="utf-8", newline="\n").write('"%s"\n{\n%s}\n' % (key_, kv.dump(it, 1)))
        at = it.get("attributes")
        lines = P.attrdesc.sort_lines(P.attrdesc.item_lines([(nn, bb.get("value")) for nn, bb in at.blocks()], ctx.defs, ctx.L))
        lines.append((it.get("item_description") or "", "neutral"))
        P.card.render_card(it.get("item_name"), summ.get("type_line", ""), lines, icon, fonts=ctx.fonts,
                           crisp=c.get("renderer") == "v2").save(os.path.join(d, "card.png"))
        summ.setdefault("gate", {})["icon_style"] = style
        summ["icon_version"] = n
        json.dump(summ, open(os.path.join(d, "summary.json"), "w"), indent=1, default=str)
        w["assets"] = list(w["assets"]) + [r for r in (rel_vtf, rel_vmt) if r not in w["assets"]]
        w["icon_version"] = n
        w["icon_pending"] = [rel_vtf, rel_vmt]
        done.append(int(k))
    if done and not a.dry_run:
        Q.journal(st, "reicon", ids=done)
        Q.save_state(st)
    print("re-rendered:" if not a.dry_run else "would re-render:", done)


if __name__ == "__main__":
    main()
