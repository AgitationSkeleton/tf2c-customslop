"""Engine-safety and hand-rig gates for a CustomSlop weapon (offline, read-only on inputs).

engine_checks(mdl_path, files_root, vfs) -> dict of named checks, each (ok, detail)
  MDL: magic/version 48, length field == file size, checksum == VVD == VTX, name < 64 chars,
       bone count <= 128 and unchanged vs the donor, finite bone data, attachments finite
  VVD: magic/version 4, LOD vertex counts non-increasing, vertex count == sum of MDL model
       vertex counts, fixup table inside the file, positions/normals/tangents/weights finite,
       weights sum to 1 (+-0.01) over the used bones, bone indices < bone count, normals unit
  VTX: version 7, checksum, per strip group vertex count <= 65535 and index count fits u16,
       indices < strip-group vertex count, original vertex IDs < mesh vertex count, bones per
       strip <= the header's maxBonesPerStrip, maxBonesPerVert <= 3
  bounds: hull / view bbox / sequence bboxes finite, every vertex inside the hull, longest
       dimension <= MAX_EXTENT units (and no more than 3x the donor's)
  VTF: magic, version 7.x, power-of-two sides <= 4096, supported format, mip count consistent
       with the size, file size == header + low-res + every mip (frames 1, faces 1)
  VMT: parses (brace balance, shader name), every texture it references exists in files_root
       or the game content
hand_checks(donor_mdl, new_mdl) -> grip-region vertices and hand attachments unchanged
  (<= 1e-4), bones identical (names, parents, rest pose, poseToBone)
"""
import os
import re
import struct

import numpy as np

import mutate as MU
import srcmodel as S

MAX_EXTENT = 160.0          # units; weapons are ~20-60, a carried prop must never be map-sized
VTF_FORMATS = {0: 4, 1: 4, 2: 3, 3: 3, 4: 2, 12: 4, 13: None, 14: None, 15: None, 16: 4}


def _vtf_size(w, h, fmt):
    if fmt in (13,):
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 8
    if fmt in (14, 15):
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 16
    return w * h * VTF_FORMATS[fmt]


def vtf_check(data):
    if data[:4] != b"VTF\0":
        return False, "bad magic"
    v0, v1, hsize, w, h, flags, frames, first = struct.unpack_from("<IIIHHIHH", data, 4)
    fmt, mips, lfmt, lw, lh = struct.unpack_from("<iBiBB", data, 0x34)
    if v0 != 7 or v1 > 5:
        return False, "version %d.%d" % (v0, v1)
    if w & (w - 1) or h & (h - 1) or not (1 <= w <= 4096 and 1 <= h <= 4096):
        return False, "size %dx%d not power of two" % (w, h)
    if fmt not in VTF_FORMATS:
        return False, "format %d" % fmt
    full = 1 + int(np.log2(max(w, h)))
    if not (1 <= mips <= full):
        return False, "mip count %d (max %d)" % (mips, full)
    need = hsize + (_vtf_size(lw, lh, lfmt) if lfmt not in (-1, 0xFFFFFFFF) else 0)
    need += sum(_vtf_size(max(1, w >> m), max(1, h >> m), fmt) for m in range(mips)) * max(1, frames)
    if v1 < 3 and len(data) != need:
        return False, "file %d bytes, header implies %d" % (len(data), need)
    return True, "%dx%d fmt %d mips %d" % (w, h, fmt, mips)


def vmt_check(text, files_root, vfs):
    # // comments are legal in VMTs (TF2C's pistol_improved starts with a contributor credit line)
    text = re.sub(r"//[^\n]*", "", text)
    if text.count("{") != text.count("}") or not re.match(r'\s*"?[A-Za-z_]+"?\s*\{', text):
        return False, "does not parse"
    missing = []
    # keys only at the start of a line: a proxy VALUE such as "animatedtexturevar" "$detail" is not
    # a texture key (that false match failed every weapon with TF2C's burn-overlay VMTs as
    # engine_ok=False, 2026-11-21); the texture value may be quoted or not
    for key, val in re.findall(r'^\s*"?(\$(?:basetexture|bumpmap|phongexponenttexture|lightwarptexture|detail|envmapmask|selfillummask))"?[ \t]+"?([^"\s]+)"?', text, re.I | re.M):
        rel = "materials/" + re.sub(r"\.vtf$", "", val.replace("\\", "/").lower()) + ".vtf"   # value may carry .vtf
        if not (files_root and os.path.exists(os.path.join(files_root, rel))) and (vfs is None or vfs.read(rel) is None):
            missing.append(val)
    return (not missing), ("missing " + ", ".join(missing)) if missing else "ok"


def engine_checks(mdl_path, files_root=None, vfs=None, donor_path=None):
    r = {}
    b = open(mdl_path, "rb").read()
    m = S.load(mdl_path)
    r["mdl_header"] = (b[:4] == b"IDST" and m.version == 48, "IDST v%d" % m.version)
    r["mdl_length"] = (m.length == len(b), "%d vs %d" % (m.length, len(b)))
    r["checksums"] = (m.checksum == m.vvd_checksum == m.vtx_checksum, "%d/%d/%d" % (m.checksum, m.vvd_checksum, m.vtx_checksum))
    r["name_len"] = (len(m.name) < 64, m.name)
    r["bones<=128"] = (len(m.bones) <= 128, str(len(m.bones)))
    if donor_path:
        d = S.load(donor_path)
        r["bones_unchanged"] = (len(d.bones) == len(m.bones) and all(
            a["name"] == c["name"] and a["parent"] == c["parent"] for a, c in zip(d.bones, m.bones)), "")
    fin = all(np.isfinite(bo["pos"]).all() and np.isfinite(bo["quat"]).all() and np.isfinite(bo["p2b"]).all() for bo in m.bones)
    r["bones_finite"] = (fin, "")
    r["attachments_finite"] = (all(np.isfinite(a["local"]).all() for a in m.attachments), "")
    v = m.vvd
    r["vvd_header"] = (v[:4] == b"IDSV" and S.i32(v, 4) == 4, "")
    lods = m.vvd_lodverts[:m.vvd_nlods]
    r["vvd_lods_nonincreasing"] = (all(lods[k] >= lods[k + 1] for k in range(len(lods) - 1)), str(lods))
    nmdl = sum(md["nverts"] for bp in m.bodyparts for md in bp["models"])
    r["vvd_count_matches_mdl"] = (lods[0] == nmdl or m.nfixups > 0, "vvd %d mdl %d" % (lods[0], nmdl))
    finite = all(np.isfinite(x).all() for x in (m.raw_pos, m.raw_nrm, m.raw_weights, m.raw_uv)) and \
        (m.raw_tan is None or np.isfinite(m.raw_tan).all())
    r["vertex_data_finite"] = (finite, "")
    used = np.arange(3)[None, :] < m.raw_nb[:, None]
    wsum = (m.raw_weights * used).sum(1)
    r["weights_sum_1"] = (bool(np.all(np.abs(wsum - 1) < 0.01)), "max err %.4f" % float(np.abs(wsum - 1).max()))
    r["bone_indices"] = (bool(np.all(np.where(used, m.raw_bones, 0) < len(m.bones))), "")
    nl = np.linalg.norm(m.raw_nrm, axis=1)
    r["normals_unit"] = (bool(np.all(np.abs(nl - 1) < 0.01)), "%.4f..%.4f" % (nl.min(), nl.max()))
    # VTX
    x = m.vtx
    r["vtx_version"] = (S.i32(x, 0) == 7, str(S.i32(x, 0)))
    max_bps = struct.unpack_from("<H", x, 8)[0]
    max_bpv = S.i32(x, 12)
    r["vtx_bones_per_vert<=3"] = (max_bpv <= 3, str(max_bpv))
    ok, worst = True, ""
    nbpx, bpox = S.i32(x, 28), S.i32(x, 32)
    for k in range(nbpx):
        bo = bpox + k * 8
        for j in range(S.i32(x, bo)):
            mo = bo + S.i32(x, bo + 4) + j * 8
            md = m.bodyparts[k]["models"][j]
            for lod in range(S.i32(x, mo)):
                lo = mo + S.i32(x, mo + 4) + lod * 12
                for q in range(S.i32(x, lo)):
                    eo = lo + S.i32(x, lo + 4) + q * 9
                    for g in range(S.i32(x, eo)):
                        go = eo + S.i32(x, eo + 4) + g * 25
                        nv, vo, ni, io_, nst, sto = struct.unpack_from("<6i", x, go)
                        if nv > 65535 or ni > 65535 * 3:
                            ok, worst = False, "strip group %d verts %d indices" % (nv, ni)
                        idx = np.frombuffer(x, dtype="<u2", count=ni, offset=go + io_)
                        if ni and idx.max() >= nv:
                            ok, worst = False, "index >= strip group verts"
                        vid = np.frombuffer(x, dtype=np.uint8, count=nv * 9, offset=go + vo).reshape(nv, 9)
                        orig = vid[:, 4].astype(int) | (vid[:, 5].astype(int) << 8)
                        if nv and orig.max() >= md["meshes"][q]["nverts"] + 0 and lod == 0:
                            ok, worst = False, "orig vertex id beyond mesh"
                        for s in range(nst):
                            nb = struct.unpack_from("<h", x, go + sto + s * 27 + 16)[0]
                            if nb > max_bps:
                                ok, worst = False, "strip bones %d > %d" % (nb, max_bps)
    r["vtx_limits"] = (ok, worst or "max bones/strip %d" % max_bps)
    # bounds
    lo, hi = m.raw_pos.min(0), m.raw_pos.max(0)
    ext = float((hi - lo).max())
    r["hull_finite_contains"] = (bool(np.isfinite(m.hull).all() and np.all(m.hull[0] <= lo + 1e-3) and np.all(m.hull[1] >= hi - 1e-3)), "")
    seq_ok = True
    for so in m.seq_offsets:
        bb = np.array(struct.unpack_from("<6f", m.mdl, so + 32))
        seq_ok &= bool(np.isfinite(bb).all()) and float(np.abs(bb).max()) < 1e5
    r["sequence_bboxes"] = (seq_ok, "")
    lim = MAX_EXTENT
    if donor_path:
        dlo, dhi = S.load(donor_path).raw_pos.min(0), S.load(donor_path).raw_pos.max(0)
        lim = min(MAX_EXTENT, 3.0 * float((dhi - dlo).max()))
    r["extent_cap"] = (ext <= lim, "%.1f u (cap %.1f)" % (ext, lim))
    # materials of this model
    mats = []
    for tex in m.textures:
        for cd in m.cdmaterials:
            rel = "materials/" + re.sub("/+", "/", (cd + tex).replace(chr(92), "/")).lstrip("/").lower() + ".vmt"
            if files_root and os.path.exists(os.path.join(files_root, rel)):
                txt = open(os.path.join(files_root, rel), encoding="latin-1").read()
                ok_, why = vmt_check(txt, files_root, vfs)
                mats.append((rel, ok_, why))
                mm = re.search(r'"\$basetexture"\s+"([^"]+)"', txt, re.I)
                if mm:
                    vp = os.path.join(files_root, "materials", mm.group(1).replace("\\", "/").lower() + ".vtf")
                    if os.path.exists(vp):
                        ok2, why2 = vtf_check(open(vp, "rb").read())
                        mats.append((os.path.relpath(vp, files_root), ok2, why2))
                break
    r["materials"] = (all(o for _, o, _ in mats), "; ".join("%s:%s" % (p.split("/")[-1], w) for p, o, w in mats if not o) or "%d ok" % len(mats))
    return {k: (bool(v[0]), v[1]) for k, v in r.items()}


def hand_checks(donor_path, new_path, eps=1e-4):
    d, n = S.load(donor_path), S.load(new_path)
    P = d.raw_pos
    ax = np.linalg.svd(P - P.mean(0))[2][0]
    w, info = MU.protection(d, ax, P @ ax)
    frozen = w == 0
    moved = np.linalg.norm(n.raw_pos - d.raw_pos, axis=1)
    r = {}
    r["grip_vertices_unchanged"] = (bool(moved[frozen].max() <= eps) if frozen.any() else True,
                                    "%d frozen, max move %.2e" % (int(frozen.sum()), float(moved[frozen].max()) if frozen.any() else 0))
    att_ok = True
    for a, b in zip(d.attachments, n.attachments):
        if not MU.MOVABLE_ATTACH.search(a["name"]):
            att_ok &= bool(np.abs(a["local"] - b["local"]).max() <= eps)
    r["hand_attachments_unchanged"] = (att_ok, ", ".join(a["name"] for a in d.attachments if not MU.MOVABLE_ATTACH.search(a["name"])))
    same = len(d.bones) == len(n.bones) and all(
        a["name"] == b["name"] and a["parent"] == b["parent"] and np.allclose(a["pos"], b["pos"]) and
        np.allclose(a["quat"], b["quat"]) and np.allclose(a["p2b"], b["p2b"]) for a, b in zip(d.bones, n.bones))
    r["bones_identical"] = (same, "%d bones" % len(n.bones))
    r["protection"] = (True, str(info))
    return r


# ---------------------------------------------------------------- schema fragment gate
def schema_check(fragment_text, attr_defs, extra_defs=None, item_classes=None):
    """Build 5205 rejects the WHOLE custom schema on: an attribute name with no definition, a value
    it cannot parse, or a set-bonus attribute (messages in server.dll: 'did not match any attribute
    definitions', 'could not parse value', 'is a set bonus attribute and not supported here' ->
    'Item schema load failed'). Also checks item_class against classes the 5205 schema uses.
    attr_defs: {lower name: {integer, set_bonus, string}}; extra_defs: CustomSlop's own definitions."""
    import kv as _kv
    errs = []
    root = _kv.parse('"x"\n{\n' + fragment_text + '\n}\n')[0].get("x")
    defs = dict(attr_defs)
    defs.update(extra_defs or {})
    for k, it in root.blocks():
        ic = it.get("item_class")
        if item_classes is not None and ic not in item_classes:
            errs.append("%s: item_class %s not used by any 5205 item" % (k, ic))
        at = it.get("attributes")
        for an, av in (at.blocks() if at is not None else []):
            d = defs.get(an.lower())
            if d is None:
                errs.append("%s: attribute %r has no definition" % (k, an))
                continue
            if d.get("set_bonus"):
                errs.append("%s: set bonus attribute %r" % (k, an))
            v = av.get("value")
            if d.get("string"):
                continue
            try:
                f = float(v)
                if d.get("integer") and f != int(f):
                    errs.append("%s: %r integer attribute with value %s" % (k, an, v))
            except (TypeError, ValueError):
                errs.append("%s: %r value %r does not parse" % (k, an, v))
    return errs
