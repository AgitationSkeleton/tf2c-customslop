"""First-person viewmodel render: weapon v_model in its idle pose + the class arms bonemerged onto
it (TF2C attach_to_hands 2), perspective camera at the eye (viewmodel origin, +X forward).
Also used by the hand-rig gate: arms_bonemerge_report() checks every bone the arms use exists in
the weapon model with the same parent name and rest pose.

render_viewmodel(ctx, vmodel_path, arms_rel, files_root=None, size=(960, 540)) -> PIL image
"""
import os
import re
import tempfile

import numpy as np
from PIL import Image

import anim
import srcmodel as S
import vtf


def skinned(m, W):
    P, out = m.raw_pos, np.zeros_like(m.raw_pos)
    N, nout = m.raw_nrm, np.zeros_like(m.raw_nrm)
    ph = np.c_[P, np.ones(len(P))]
    for j in range(3):
        for k in np.unique(m.raw_bones[:, j]):
            sel = (m.raw_bones[:, j] == k) & (m.raw_nb > j)
            if not sel.any():
                continue
            M = W[k] @ m.bones[k]["p2b"]
            out[sel] += m.raw_weights[sel, j:j + 1] * (ph[sel] @ M.T)[:, :3]
            nout[sel] += m.raw_weights[sel, j:j + 1] * (N[sel] @ M[:3, :3].T)
    nout /= np.linalg.norm(nout, axis=1, keepdims=True) + 1e-9
    return out, nout


def bonemerge(arms, vm_names, vm_W):
    """Arms bone matrices: a bone named like a weapon bone takes the weapon's idle matrix;
    others keep their rest offset from their (merged) parent."""
    W = []
    for k, bo in enumerate(arms.bones):
        if bo["name"] in vm_names:
            W.append(vm_W[vm_names[bo["name"]]])
            continue
        L = np.eye(4)
        L[:3, :3] = S.quat_to_mat(bo["quat"])
        L[:3, 3] = bo["pos"]
        W.append(L if bo["parent"] < 0 else W[bo["parent"]] @ L)
    return W


def arms_bonemerge_report(vm, arms):
    """Per side (L/R): if the weapon animates that hand (has bip_hand_<side>), every arms bone of that
    side the arms mesh is skinned to must exist in the weapon model (by name), otherwise that hand
    would bonemerge partially and deform. One-handed weapons legitimately omit the other arm (it stays
    off-screen at rest, as in stock TF2). At least one complete side is required; shared bones
    (spine/collar/root) must all exist when any side is animated."""
    used = set(arms.raw_bones[arms.raw_weights > 0].ravel().tolist())
    names = {b["name"] for b in vm.bones}
    out, any_side = {}, False
    for side in ("L", "R"):
        if "bip_hand_" + side not in names:
            out[side] = "not animated (one-handed)"
            continue
        req = [arms.bones[k]["name"] for k in used if arms.bones[k]["name"].endswith("_" + side)]
        miss = sorted(n for n in req if n not in names)
        out[side] = "complete" if not miss else "missing %s" % miss
        any_side |= not miss
    shared = [arms.bones[k]["name"] for k in used if not arms.bones[k]["name"].endswith(("_L", "_R"))]
    shared_missing = sorted(n for n in shared if n not in names)
    ok = any_side and all(v != "" and not v.startswith("missing") for v in out.values()) and not shared_missing
    return dict(arms_bones_used=len(used), sides=out, shared_missing=shared_missing, ok=ok)


def textures_for(ctx, m, files_root):
    import pipeline
    out = {}
    for k, t in enumerate(m.textures):
        out[k] = None
        for cd in m.cdmaterials:
            rel = "materials/" + re.sub("/+", "/", (cd + t).replace(chr(92), "/")).lstrip("/").lower() + ".vmt"
            txt = None
            if files_root and os.path.exists(os.path.join(files_root, rel)):
                txt = open(os.path.join(files_root, rel), encoding="latin-1").read()
            elif ctx.fs.read(rel) is not None:
                _, txt = pipeline.resolve_vmt(ctx, pipeline._One(cd), t)
            if txt:
                mm = re.search(r'"\$basetexture"\s+"([^"]+)"', txt, re.I)
                if mm:
                    bt = "materials/" + mm.group(1).replace("\\", "/").lower() + ".vtf"
                    raw = open(os.path.join(files_root, bt), "rb").read() if files_root and os.path.exists(
                        os.path.join(files_root, bt)) else ctx.fs.read(bt)
                    if raw:
                        out[k] = vtf.decode(raw)[2]
                break
    return out


def materials_for(ctx, m, files_root):
    """{texture index: srcshade material dict} from each texture's VMT ($phong*, $lightwarptexture,
    $rimlight*, $selfillum, exponent / bump textures). Reads the generated files first, then ctx.fs."""
    import pipeline
    import srcshade

    def read_vtf(rel):
        raw = open(os.path.join(files_root, rel), "rb").read() if files_root and os.path.exists(
            os.path.join(files_root, rel)) else ctx.fs.read(rel)
        try:
            return vtf.decode(raw)[2] if raw else None
        except Exception:
            return None
    out = {}
    for k, t in enumerate(m.textures):
        out[k] = {}
        for cd in m.cdmaterials:
            rel = "materials/" + re.sub("/+", "/", (cd + t).replace(chr(92), "/")).lstrip("/").lower() + ".vmt"
            txt = None
            if files_root and os.path.exists(os.path.join(files_root, rel)):
                txt = open(os.path.join(files_root, rel), encoding="latin-1").read()
            elif ctx.fs.read(rel) is not None:
                _, txt = pipeline.resolve_vmt(ctx, pipeline._One(cd), t)
            if txt:
                out[k] = srcshade.parse_vmt(txt, read_vtf)
                break
    # stock weapon lightwarp (used only if the calibrated rig says materials without one need it)
    fw = read_vtf("materials/models/lightwarps/weapon_lightwarp.vtf")
    for k in out:
        if fw is not None:
            out[k]["fallback_warp"] = fw[0, :, :3].astype(np.float32) / 255.0
    return out


def raster(items, size, fov=54.0, mats_list=None):
    """mats_list (v2): per item {texture index: srcshade material} -> Source-like shading."""
    Wd, Ht = size
    v2 = mats_list is not None
    if v2:
        nb = np.zeros((Ht, Wd, 3), np.float32)
        ab = np.zeros((Ht, Wd, 3), np.float32)
        bab = np.ones((Ht, Wd), np.float32)
        uvb = np.zeros((Ht, Wd, 2), np.float32)
        mb = np.full((Ht, Wd), -1, np.int32)
        allm = {}
        for ii, ml in enumerate(mats_list):
            for k, v in (ml or {}).items():
                allm[ii * 1000 + k] = v
    f = (Wd / 2) / np.tan(np.radians(fov / 2))
    zbuf = np.full((Ht, Wd), np.inf)
    col = np.zeros((Ht, Wd, 3))
    alpha = np.zeros((Ht, Wd))
    L1 = np.array([0.3, 0.6, 0.75]); L1 /= np.linalg.norm(L1)
    for ii, (P, N, uv, tris, tex) in enumerate(items):
        x = P[:, 0]
        ok = x > 1.0
        sx = Wd / 2 - P[:, 1] / np.maximum(x, 1e-3) * f
        sy = Ht / 2 - P[:, 2] / np.maximum(x, 1e-3) * f
        for mat, T in tris:
            tx = tex.get(mat)
            th, tw = (tx.shape[0], tx.shape[1]) if tx is not None else (1, 1)
            for a, b_, c in T:
                if not (ok[a] and ok[b_] and ok[c]):
                    continue
                xa, xb, xc = sx[a], sx[b_], sx[c]
                ya, yb, yc = sy[a], sy[b_], sy[c]
                x0, x1 = int(max(0, np.floor(min(xa, xb, xc)))), int(min(Wd - 1, np.ceil(max(xa, xb, xc))))
                y0, y1 = int(max(0, np.floor(min(ya, yb, yc)))), int(min(Ht - 1, np.ceil(max(ya, yb, yc))))
                if x1 < x0 or y1 < y0 or (x1 - x0) * (y1 - y0) > Wd * Ht:
                    continue
                den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
                if abs(den) < 1e-12:
                    continue
                gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
                w0 = ((yb - yc) * (gx - xc) + (xc - xb) * (gy - yc)) / den
                w1 = ((yc - ya) * (gx - xc) + (xa - xc) * (gy - yc)) / den
                w2 = 1 - w0 - w1
                ins = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
                if not ins.any():
                    continue
                z = w0 * x[a] + w1 * x[b_] + w2 * x[c]
                zb = zbuf[y0:y1 + 1, x0:x1 + 1]
                win = ins & (z < zb)
                if not win.any():
                    continue
                zb[win] = z[win]
                n = (w0[..., None] * N[a] + w1[..., None] * N[b_] + w2[..., None] * N[c])[win]
                n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
                u = (w0[..., None] * uv[a] + w1[..., None] * uv[b_] + w2[..., None] * uv[c])[win]
                if tx is not None:
                    tt = tx[(np.mod(u[:, 1], 1) * th).astype(int).clip(0, th - 1),
                            (np.mod(u[:, 0], 1) * tw).astype(int).clip(0, tw - 1)]
                    alb = tt[:, :3] / 255.0
                    if v2 and tt.shape[1] > 3:
                        bab[y0:y1 + 1, x0:x1 + 1][win] = tt[:, 3] / 255.0
                else:
                    alb = np.full((win.sum(), 3), 0.6)
                if v2:
                    nb[y0:y1 + 1, x0:x1 + 1][win] = n
                    ab[y0:y1 + 1, x0:x1 + 1][win] = alb
                    uvb[y0:y1 + 1, x0:x1 + 1][win] = u
                    mb[y0:y1 + 1, x0:x1 + 1][win] = ii * 1000 + mat
                hl = (n @ L1) * 0.5 + 0.5
                col[y0:y1 + 1, x0:x1 + 1][win] = np.clip(alb * (0.3 + 0.75 * hl ** 2)[:, None], 0, 1)
                alpha[y0:y1 + 1, x0:x1 + 1][win] = 1
    bg = np.array([0.27, 0.3, 0.34])
    if v2:
        import srcshade as SS
        col = SS.shade(nb, ab, bab, uvb, mb, alpha, allm)
    img = col * alpha[..., None] + bg * (1 - alpha[..., None])
    return Image.fromarray((img * 255).astype(np.uint8), "RGB")


def render_viewmodel(ctx, vmodel_path, arms_rel, files_root=None, size=(960, 540), v2=False):
    import pipeline
    vm = S.load(vmodel_path)
    W = anim.pose(vm)
    P, N = skinned(vm, W)
    items = [(P, N, vm.raw_uv, vm.tris, {k: v for k, v in textures_for(ctx, vm, files_root).items()})]
    ml = [materials_for(ctx, vm, files_root)] if v2 else None
    report = None
    tmp = tempfile.mkdtemp()
    ap = pipeline.extract_model(ctx, arms_rel, tmp)
    if os.path.exists(ap):
        arms = S.load(ap)
        names = {b["name"]: k for k, b in enumerate(vm.bones)}
        AW = bonemerge(arms, names, W)
        AP, AN = skinned(arms, AW)
        items.append((AP, AN, arms.raw_uv, arms.tris, textures_for(ctx, arms, None)))
        if v2:
            ml.append(materials_for(ctx, arms, None))
        report = arms_bonemerge_report(vm, arms)
    eye = raster(items, size, mats_list=ml)
    # side view of the same idle pose (arms + weapon), to see the mutation from the outside
    allp = np.vstack([it[0] for it in items[:1]])
    cen = (allp.min(0) + allp.max(0)) / 2
    ext = float(np.linalg.norm(allp.max(0) - allp.min(0)))
    a = np.radians(75)
    R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    side_items = [((P_ - cen) @ R.T + np.array([ext * 1.6, 0, 0]), N_ @ R.T, uv_, tr_, tx_)
                  for P_, N_, uv_, tr_, tx_ in items]
    side = raster(side_items, size, fov=40.0, mats_list=ml)
    both = Image.new("RGB", (size[0] * 2, size[1]))
    both.paste(eye, (0, 0))
    both.paste(side, (size[0], 0))
    return both, report
