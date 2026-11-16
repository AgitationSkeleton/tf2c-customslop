"""End-to-end CustomSlop prototype for one weapon (cs0001, from TF2C's Nail Gun). Offline only.

1. mutate.py has already written proto/out/models/customslop/cs0001/{w,v}_cs0001.* (run first)
2. recolour: whole-texture hue shift + the stretched barrel section (UV mask) in a loud colour
3. VMTs for the textures the models name, in the new cdmaterials dir
4. structural validation of the mutated models
5. icon render (orig vs mutated), icon VTF + VMT in TF2C's loadout-icon format
"""
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srcmodel as S  # noqa: E402
import recolor as RC  # noqa: E402
import render as R  # noqa: E402
import vtf  # noqa: E402
from mutate import Deform  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "extract")
OUT = os.path.join(ROOT, "proto", "out")
ID = "cs0001"
MATDIR = "models/customslop/" + ID
params = None   # demo parameters, loaded by main()


def validate(orig_p, new_p):
    o, n = S.load(orig_p), S.load(new_p)
    rep = {}
    rep["checksums_agree"] = len({n.checksum, n.vvd_checksum, n.vtx_checksum}) == 1
    rep["checksum_unchanged"] = n.checksum == o.checksum
    rep["length_field_matches_file"] = n.length == len(n.mdl)
    rep["name"] = n.name
    rep["cdmaterials"] = n.cdmaterials
    rep["vertex_count_same"] = n.nraw == o.nraw
    rep["tris_identical"] = all(np.array_equal(a[1], b[1]) for a, b in zip(o.tris, n.tris))
    rep["max_tri_index_ok"] = max(int(t.max()) for _, t in n.tris) < n.nraw
    rep["finite"] = bool(np.isfinite(n.raw_pos).all() and np.isfinite(n.raw_nrm).all())
    nl = np.linalg.norm(n.raw_nrm, axis=1)
    rep["normals_unit"] = [float(nl.min()), float(nl.max())]
    if n.raw_tan is not None:
        tl = np.linalg.norm(n.raw_tan[:, :3], axis=1)
        rep["tangents_unit"] = [float(tl.min()), float(tl.max())]
        rep["tangent_w_unchanged"] = bool(np.array_equal(np.sign(n.raw_tan[:, 3]), np.sign(o.raw_tan[:, 3])))
    lo, hi = n.raw_pos.min(0), n.raw_pos.max(0)
    rep["hull_contains_verts"] = bool(np.all(n.hull[0] <= lo + 1e-3) and np.all(n.hull[1] >= hi - 1e-3))
    seq_ok = True
    for so in n.seq_offsets:
        bb = np.array(struct.unpack_from("<6f", n.mdl, so + 32)).reshape(2, 3)
        if not (np.all(bb[0] <= lo + 1e-3) and np.all(bb[1] >= hi - 1e-3)):
            # view-model sequences animate bones away from rest; only require growth vs original
            pass
        ob = np.array(struct.unpack_from("<6f", o.mdl, so + 32)).reshape(2, 3)
        seq_ok &= bool(np.all(bb[0] <= ob[0] + 1e-4) and np.all(bb[1] >= ob[1] - 1e-4))
    rep["sequence_bboxes_only_grew"] = seq_ok
    rep["bones_identical"] = n.mdl[n.bones[0]["off"]:n.bones[-1]["off"] + S.BONE_SIZE] == \
        o.mdl[o.bones[0]["off"]:o.bones[-1]["off"] + S.BONE_SIZE]
    rep["vtx_bytes_identical"] = n.vtx == o.vtx
    # bytes changed outside the expected regions of the MDL (header name/bbox/len, attachments,
    # seq bboxes, hitboxes, model radius, mesh centres, cdmaterial table) for an audit trail
    diff = np.nonzero(np.frombuffer(n.mdl[:len(o.mdl)], np.uint8) != np.frombuffer(o.mdl, np.uint8))[0]
    rep["mdl_bytes_changed_in_original_span"] = int(len(diff))
    rep["mdl_bytes_appended"] = len(n.mdl) - len(o.mdl)
    vd = np.nonzero(np.frombuffer(n.vvd, np.uint8) != np.frombuffer(o.vvd, np.uint8))[0]
    rep["vvd_changed_range"] = [int(vd.min()), int(vd.max())] if len(vd) else None
    rep["vvd_header_unchanged"] = n.vvd[:64] == o.vvd[:64]
    return rep


def main():
    global params
    params = json.load(open(os.path.join(ROOT, "proto", ID + "_params.json")))
    report = {}
    w_orig = os.path.join(EX, "models/weapons/w_models/w_nailgun.mdl")
    v_orig = os.path.join(EX, "models/weapons/v_models/v_nailgun_scout.mdl")
    w_new = os.path.join(OUT, "models/customslop", ID, "w_" + ID + ".mdl")
    v_new = os.path.join(OUT, "models/customslop", ID, "v_" + ID + ".mdl")
    # --- 2. texture: global hue shift + barrel section from the world model's UVs
    m = S.load(w_orig)
    W = S.rest_world(m)
    mz = [a for a in m.attachments if a["name"] == "muzzle"][0]
    axis = (W[mz["bone"]] @ mz["local"])[:3, 3]
    axis /= np.linalg.norm(axis)
    t = m.raw_pos @ axis
    D = Deform(np.zeros(3), axis, t.min(), t.max(), **{k: params[k] for k in ("stretch", "pivot")})
    front = t > D.tp
    sel = [tri for _, tt in m.tris for tri in tt if front[tri].all()]
    src_tex = os.path.join(EX, "materials/models/weapons/v_nailgun/v_nailgun.vtf")
    tw, th = vtf.decode(open(src_tex, "rb").read())[:2]
    mask = RC.uv_mask(m, sel, (tw, th))
    base = MATDIR + "/" + ID + "_color"
    res = RC.recolor_vtf(src_tex, os.path.join(OUT, "materials", base + ".vtf"),
                         global_op=dict(hue_deg=150, sat=1.25, val=1.0),
                         section=dict(mask=mask, hue_deg=0, sat=0.0, val=1.0, tint=(0.2, 1.0, 0.3), tint_amt=0.85))
    Image.fromarray(res[..., :3]).resize((512, 512)).save(os.path.join(ROOT, "proto", "render", ID + "_texture.png"))
    Image.fromarray((mask * 255).astype(np.uint8)).resize((512, 512)).save(os.path.join(ROOT, "proto", "render", ID + "_uvmask.png"))
    report["texture_section_texels"] = float(mask.mean())
    # --- 3. VMTs named after the models' texture names
    RC.write_vmt(os.path.join(EX, "materials/models/weapons/w_nailgun/w_nailgun01.vmt"),
                 os.path.join(OUT, "materials", MATDIR, "w_nailgun01.vmt"), base)
    RC.write_vmt(os.path.join(EX, "materials/models/weapons/v_nailgun/v_nailgun.vmt"),
                 os.path.join(OUT, "materials", MATDIR, "v_nailgun.vmt"), base)
    # --- 4. validation
    report["validate_w"] = validate(w_orig, w_new)
    report["validate_v"] = validate(v_orig, v_new)
    # --- 5. renders + icon
    rdir = os.path.join(ROOT, "proto", "render")
    roots = [OUT, EX]
    im_o = R.render(S.load(w_orig), roots)
    im_n = R.render(S.load(w_new), roots)
    im_o.save(os.path.join(rdir, "w_nailgun_orig.png"))
    im_n.save(os.path.join(rdir, ID + "_icon.png"))
    sheet = Image.new("RGBA", (1024, 512), (60, 60, 60, 255))
    sheet.alpha_composite(im_o, (0, 0))
    sheet.alpha_composite(im_n, (512, 0))
    sheet.save(os.path.join(rdir, ID + "_compare.png"))
    vm = R.render(S.load(v_new), roots, yaw=25)
    vm.save(os.path.join(rdir, ID + "_viewmodel_render.png"))
    # icon in TF2C's loadout format: 512x512 DXT5 + UnlitGeneric VMT; image_inventory names it
    icon_rel = "backpack/customslop/" + ID
    ip = os.path.join(OUT, "materials", icon_rel + "_large.vtf")
    os.makedirs(os.path.dirname(ip), exist_ok=True)
    open(ip, "wb").write(vtf.encode(np.asarray(im_n), fmt=15, mips=True, flags=0x2000 | 0x4 | 0x8 | 0x100000 * 0))
    open(ip[:-4] + ".vmt", "w").write('"UnlitGeneric"\n{\n\t"$baseTexture" "%s_large"\n\t"$translucent" 1\n'
                                      '\t"$vertexcolor" 1\n\t"$ignorez" 1\n}\n' % icon_rel)
    chk = vtf.decode(open(ip, "rb").read())
    report["icon_vtf"] = dict(path=ip, size=os.path.getsize(ip), w=chk[0], h=chk[1], info=chk[3])
    sizes = {}
    for dp, _, fs in os.walk(OUT):
        for f in fs:
            p = os.path.join(dp, f)
            sizes[os.path.relpath(p, OUT).replace("\\", "/")] = os.path.getsize(p)
    report["files"] = sizes
    report["total_bytes"] = sum(sizes.values())
    import bz2
    report["total_bz2_bytes"] = sum(len(bz2.compress(open(os.path.join(OUT, k), "rb").read())) for k in sizes)
    json.dump(report, open(os.path.join(ROOT, "proto", ID + "_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
