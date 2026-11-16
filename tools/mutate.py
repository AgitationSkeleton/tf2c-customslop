"""CustomSlop model mutation prototype: binary-patch a compiled Source model (no decompile).

Edits a *copy* of MDL/VVD/VTX(/PHY):
  * geometry: a smooth, piecewise deformation in the weapon's local frame applied to every VVD
    vertex (all LODs share the VVD, so LODs stay consistent; VTX holds indices only and is
    copied byte-for-byte). Normals use the inverse-transpose of the numeric Jacobian, tangents
    the Jacobian itself.
      - stretch: everything past a pivot along the muzzle axis is scaled by S along the axis
                 (barrel longer/shorter; the grip side is untouched so hands still fit)
      - bulge:   radial scale around the axis with a Gaussian profile at a chosen station
      - bend:    the front part curves (rotation about a perpendicular axis growing with distance)
  * attachments (muzzle, eject ...) are moved with the geometry,
  * bounding boxes: hull, view bbox, every sequence bbox, hitboxes, model bounding radius,
    mesh centres are re-derived/expanded,
  * identity: the internal model name (header name[64]) is set to the new path,
  * materials: a new cdmaterials directory is prepended (string + offset table appended to the
    end of the file, header length updated) so the model resolves recoloured VMTs first; the
    old directories stay as fallbacks.
The checksum is left untouched: MDL, VVD, VTX and PHY must keep agreeing with each other.

usage: python -I mutate.py <src.mdl> <out_root> <new rel path e.g. models/customslop/cs0001/w_cs0001.mdl>
          --matdir models/customslop/cs0001 [--stretch 1.6] [--pivot 0.35] [--bulge 0.4]
          [--bulge-at 0.7] [--bulge-width 0.12] [--bend 0] [--axis-from muzzle]
          [--params params.json]
"""
import argparse
import json
import os
import shutil
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srcmodel as S  # noqa: E402


class Deform:
    """Deformation in model space. Frame: origin o, unit axis a (toward the muzzle), u, v."""

    def __init__(self, o, a, tmin, tmax, stretch=1.0, pivot=0.35, bulge=0.0, bulge_at=0.7,
                 bulge_width=0.12, bend_deg=0.0, droop=0.0, twist_deg=0.0, flare=0.0, squash=1.0,
                 wobble=0.0, wobble_freq=3.0, bend_plane=0.0, centre=None):
        self.o, self.a = o, a / np.linalg.norm(a)
        # v = "up" (world z projected off the axis), u = sideways
        up = np.array([0, 0, 1.0]) if abs(self.a[2]) < 0.9 else np.array([1.0, 0, 0])
        self.v = up - self.a * (up @ self.a)
        self.v /= np.linalg.norm(self.v)
        self.u = np.cross(self.v, self.a)
        self.tmin, self.tmax = tmin, tmax
        L = tmax - tmin
        self.tp = tmin + pivot * L          # pivot station
        self.s = stretch
        self.bulge, self.tb, self.wb = bulge, tmin + bulge_at * L, max(1e-3, bulge_width * L)
        self.bend = np.radians(bend_deg)
        self.bend_plane = np.radians(bend_plane)     # 0 = sideways, 90 = up/down
        self.droop, self.twist = droop, np.radians(twist_deg)
        self.flare, self.squash, self.wobble, self.wf = flare, squash, wobble, wobble_freq
        # radial effects act about the weapon's own centre line (not the origin), so a barrel
        # inflates around itself instead of drifting
        self.c_uv = np.zeros(2) if centre is None else np.array(centre, float)
        self.L = L

    def __call__(self, P):
        P = np.atleast_2d(P)
        d = P - self.o
        t = d @ self.a
        pu, pv = d @ self.u - self.c_uv[0], d @ self.v - self.c_uv[1]
        f = np.clip((t - self.tp) / max(1e-6, self.tmax - self.tp), 0, 1)     # 0 at pivot .. 1 at tip
        # bulge / inflation of a section (evaluated at the undeformed station)
        g = 1.0 + self.bulge * np.exp(-0.5 * ((t - self.tb) / self.wb) ** 2)
        # blunderbuss flare: the last quarter opens up like a bell
        if self.flare:
            fl = np.clip((t - (self.tmax - 0.25 * self.L)) / (0.25 * self.L), 0, 1)
            g = g * (1.0 + self.flare * fl ** 2)
        pu, pv = pu * g, pv * g
        # squash / stretch of the cross-section past the pivot
        if self.squash != 1.0:
            k = 1 + (self.squash - 1) * f
            pu, pv = pu * k, pv / k
        # twist about the barrel axis, growing toward the tip
        if self.twist:
            ang = self.twist * f
            pu, pv = pu * np.cos(ang) - pv * np.sin(ang), pu * np.sin(ang) + pv * np.cos(ang)
        # wobble: a gentle wave along the front part
        if self.wobble:
            ph = (t - self.tp) / self.L * 2 * np.pi * self.wf
            pu = pu + self.wobble * self.L * f * np.sin(ph)
            pv = pv + self.wobble * self.L * f * np.cos(ph * 0.7)
        pu, pv = pu + self.c_uv[0], pv + self.c_uv[1]
        # droop: the front sags under its own weight (quadratic curve downwards)
        if self.droop:
            pv = pv - self.droop * self.L * f ** 2
        # stretch past the pivot
        t2 = np.where(t > self.tp, self.tp + (t - self.tp) * self.s, t)
        # bend: rotate the front part about the v axis by an angle growing with distance
        if self.bend:
            # rotate in the plane (axis, w) with w = u*cos(plane) + v*sin(plane)
            cp, sp = np.cos(self.bend_plane), np.sin(self.bend_plane)
            pw = pu * cp + pv * sp
            pn = -pu * sp + pv * cp
            beyond = np.clip((t2 - self.tp) / max(1e-6, (self.tmax - self.tp) * self.s), 0, 1)
            ang = self.bend * beyond ** 2
            r = t2 - self.tp
            front = t2 > self.tp
            t3 = self.tp + r * np.cos(ang) - pw * np.sin(ang)
            pw2 = r * np.sin(ang) + pw * np.cos(ang)
            t2 = np.where(front, t3, t2)
            pw = np.where(front, pw2, pw)
            pu, pv = pw * cp - pn * sp, pw * sp + pn * cp
        return self.o + np.outer(t2, self.a) + np.outer(pu, self.u) + np.outer(pv, self.v)

    def jacobian(self, P, eps=1e-3):
        J = np.zeros((len(P), 3, 3))
        for k in range(3):
            e = np.zeros(3)
            e[k] = eps
            J[:, :, k] = (self(P + e) - self(P - e)) / (2 * eps)
        return J


def put(buf, off, fmt, *vals):
    struct.pack_into(fmt, buf, off, *vals)


def bbox_corners(bb):
    lo, hi = bb
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def grow_bbox(bb, D, extra_pts=None):
    """Union of the old box and the deformed old box (+ extra points)."""
    pts = [bbox_corners(bb), D(bbox_corners(bb))]
    if extra_pts is not None:
        pts.append(extra_pts)
    allp = np.vstack(pts)
    return np.array([allp.min(0), allp.max(0)])


import re  # noqa: E402

HAND_BONES = re.compile(r"(hand|finger|thumb|index|middle|ring|pinky|arm|collar|clavicle|wrist|bip_)", re.I)
MOVABLE_ATTACH = re.compile(r"(muzzle|eject|brass|shell|mag|clip|backblast|flash|tracer|barrel|tip|exhaust|smoke)", re.I)
GRIP_INNER, GRIP_OUTER = 0.14, 0.30        # fractions of the weapon length around each hand
COARSE_EDGE = 0.12                          # a part with an edge longer than this x weapon length is "coarse"


def is_coarse(m, frac=0.5):
    """True if more than `frac` of the vertices sit in coarse parts (a part with an edge longer
    than COARSE_EDGE x the weapon length along its axis); those parts are deformed piecewise-affine,
    so a mostly-coarse model only gets the affine-friendly effects."""
    P = m.raw_pos
    ax = np.linalg.svd(P - P.mean(0))[2][0]
    t = P @ ax
    L = max(1e-3, float(t.max() - t.min()))
    edge = np.zeros(m.nraw)
    for _, T in m.tris:
        e = np.abs(t[T][:, [0, 1, 2]] - t[T][:, [1, 2, 0]]).max(1)
        for j in range(3):
            np.maximum.at(edge, T[:, j], e)
    comp = components(m)
    coarse_v = 0
    for k in np.unique(comp):
        sel = comp == k
        if edge[sel].max() > COARSE_EDGE * L:
            coarse_v += sel.sum()
    return coarse_v / m.nraw > frac


def protection(m, axis, t):
    """Per-vertex deformation weight. Vertices skinned (any weight) to hand/arm/finger bones get 0.
    The grip region gets 0 near every hand and ramps to 1 further away: hand positions come from the
    idle pose of the view model (bip_hand_L/R and finger bones, decoded from the MDL), or the model
    origin for world/c_models (the player's hand bonemerges there)."""
    L = max(1e-3, float(t.max() - t.min()))
    hand_ids = [k for k, b in enumerate(m.bones) if HAND_BONES.search(b["name"])]
    skinned_to_hand = np.zeros(m.nraw, bool)
    for j in range(3):
        skinned_to_hand |= np.isin(m.raw_bones[:, j], hand_ids) & (m.raw_weights[:, j] > 0) & (m.raw_nb > j)
    grips, space = [], "bind"
    hb = [k for k, b in enumerate(m.bones) if re.search(r"(hand|thumb|index|middle|ring|pinky)", b["name"], re.I)]
    if hb:
        import anim
        W = anim.pose(m)
        # vertex positions in the idle pose (rigid by primary bone), hands at their idle positions
        Pi = np.zeros_like(m.raw_pos)
        for k in np.unique(m.raw_bones[:, 0]):
            sel = m.raw_bones[:, 0] == k
            M = W[k] @ m.bones[k]["p2b"]
            Pi[sel] = (np.c_[m.raw_pos[sel], np.ones(sel.sum())] @ M.T)[:, :3]
        grips = [W[k][:3, 3] for k in hb]
        pts, space = Pi, "idle"
    else:
        pts, grips = m.raw_pos, [np.zeros(3)]
    d = np.min(np.stack([np.linalg.norm(pts - g, axis=1) for g in grips]), axis=0)
    w = np.clip((d - GRIP_INNER * L) / ((GRIP_OUTER - GRIP_INNER) * L), 0, 1)
    w = w * w * (3 - 2 * w)                    # smoothstep
    w[skinned_to_hand] = 0
    return w, dict(space=space, hands=len(grips), frozen=int((w == 0).sum()), partial=int(((w > 0) & (w < 1)).sum()),
                   hand_skinned=int(skinned_to_hand.sum()), length=round(L, 2))


def attach_weight(p, P, w):
    """Deformation weight at an attachment = weight of the nearest vertex."""
    return float(w[np.argmin(np.linalg.norm(P - p, axis=1))])


def components(m):
    """Connected parts of the mesh: union-find over LOD0 triangles after welding vertices that
    share a position (UV seams duplicate vertices). Vertices used only by lower LODs join the
    part of their nearest LOD0 vertex."""
    key = np.round(m.raw_pos * 1000).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    parent = np.arange(weld.max() + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for _, t in m.tris:
        for a, b, c in weld[t]:
            ra, rb, rc = find(a), find(b), find(c)
            parent[rb] = ra
            parent[find(rc)] = ra
    roots = np.array([find(x) for x in range(len(parent))])
    _, lab = np.unique(roots, return_inverse=True)
    comp = lab[weld]
    used = np.zeros(m.nraw, bool)
    for _, t in m.tris:
        used[t.ravel()] = True
    if (~used).any():
        up = np.nonzero(used)[0]
        for i in np.nonzero(~used)[0]:
            comp[i] = comp[up[np.argmin(np.linalg.norm(m.raw_pos[up] - m.raw_pos[i], axis=1))]]
    return comp


def mutate(src, out_root, rel, matdir, params):
    m = S.load(src)
    W = S.rest_world(m)
    P = m.raw_pos
    # weapon frame: axis from the root bone origin toward the muzzle attachment if present
    o = np.zeros(3)
    mz = [a for a in m.attachments if a["name"].lower() == "muzzle"]
    # long axis = first principal component of the mesh, pointed toward the muzzle (or toward
    # the far end from the origin when there is no muzzle, e.g. melee: the handle sits at 0)
    c = P.mean(0)
    axis = np.linalg.svd(P - c)[2][0]
    ref = ((W[mz[0]["bone"]] @ mz[0]["local"])[:3, 3] - c) if mz else c
    if params.get("axis") == "muzzle" and mz:
        axis = (W[mz[0]["bone"]] @ mz[0]["local"])[:3, 3] - o
    elif axis @ ref < 0:
        axis = -axis
    axis = axis / np.linalg.norm(axis)
    t = (P - o) @ axis
    # centre line of the front part (radial effects act about it)
    tmp = Deform(o, axis, t.min(), t.max())
    front = t > t.min() + 0.6 * (t.max() - t.min())
    centre = [float(((P[front] - o) @ tmp.u).mean()), float(((P[front] - o) @ tmp.v).mean())] if front.any() else None
    D = Deform(o, axis, t.min(), t.max(), stretch=params.get("stretch", 1.0),
               pivot=params.get("pivot", 0.35), bulge=params.get("bulge", 0.0),
               bulge_at=params.get("bulge_at", 0.7), bulge_width=params.get("bulge_width", 0.12),
               bend_deg=params.get("bend", 0.0), droop=params.get("droop", 0.0),
               twist_deg=params.get("twist", 0.0), flare=params.get("flare", 0.0),
               squash=params.get("squash", 1.0), wobble=params.get("wobble", 0.0),
               wobble_freq=params.get("wobble_freq", 3.0), bend_plane=params.get("bend_plane", 0.0),
               centre=centre)
    # optional per-part affine "misshaping": every connected part (welded by position) gets its
    # own scale about its centroid. Affine per part = no faceting artefacts on low-poly parts.
    A = np.repeat(np.eye(3)[None], m.nraw, axis=0)
    P0 = P
    comp_info = None
    if params.get("parts"):
        comp = components(m)
        rng = np.random.default_rng(params["parts"].get("seed", 1))
        lo, hi = params["parts"].get("scale", [0.7, 1.5])
        nparts = comp.max() + 1
        pick = rng.permutation(nparts)[:max(1, int(nparts * params["parts"].get("fraction", 0.5)))]
        P0 = P.copy()
        for k in pick:
            sel = comp == k
            if sel.sum() < 12:
                continue
            s = np.exp(rng.uniform(np.log(lo), np.log(hi), 3))
            Ak = np.diag(s)
            ck = P[sel].mean(0)
            P0[sel] = (P[sel] - ck) @ Ak.T + ck
            A[sel] = Ak
        comp_info = dict(parts=int(nparts), scaled=int(len(pick)))
    # hand-rig protection: weight 0 = untouched (grip / hand-skinned), 1 = fully deformed
    wprot, prot_info = protection(m, axis, t)
    G = D(P0)
    JG = D.jacobian(P0) @ A
    # coarse parts (long triangles relative to the weapon) get the piecewise-affine version of the
    # effect: the deformation's value + Jacobian at the part's centroid, applied rigidly-affinely,
    # so long flat faces never twist into each other (the faceting seen on the rocket launcher)
    comp_all = components(m)
    Lw = max(1e-3, float(t.max() - t.min()))
    edge = np.zeros(m.nraw)
    for _, T in m.tris:
        e = np.abs((P[T] @ axis)[:, [0, 1, 2]] - (P[T] @ axis)[:, [1, 2, 0]]).max(1)
        for j in range(3):
            np.maximum.at(edge, T[:, j], e)
    coarse_parts = 0
    coarse = {}
    for k in np.unique(comp_all):
        sel = comp_all == k
        if edge[sel].max() > COARSE_EDGE * Lw:
            # linearise at the part's back end (the joint nearest the grip), so a rigid barrel
            # pivots where it meets the receiver instead of drifting off it
            tt = P0[sel] @ axis
            cc = P0[sel][np.argsort(tt)[:max(1, len(tt) // 20)]].mean(0, keepdims=True)
            coarse[k] = (cc, D(cc)[0], D.jacobian(cc)[0])
            coarse_parts += 1
    if coarse:
        ck = list(coarse)
        cverts = {k: P[comp_all == k] for k in ck}
        for k in np.unique(comp_all):
            sel = comp_all == k
            use = k if k in coarse else None
            if use is None:      # small parts touching a coarse part move with it (sights, rings, rails)
                cen = P[sel].mean(0)
                dist = {c: float(np.min(np.linalg.norm(cverts[c] - cen, axis=1))) for c in ck}
                best = min(dist, key=dist.get)
                if dist[best] < 0.08 * Lw:
                    use = best
            if use is not None:
                cc, Dc, Jc = coarse[use]
                G[sel] = Dc + (P0[sel] - cc[0]) @ Jc.T
                JG[sel] = Jc @ A[sel]
    newP = P + wprot[:, None] * (G - P)
    J = np.eye(3)[None] + wprot[:, None, None] * (JG - np.eye(3)[None])
    Jit = np.linalg.inv(J).transpose(0, 2, 1)
    newN = np.einsum("nij,nj->ni", Jit, m.raw_nrm)
    newN /= np.linalg.norm(newN, axis=1, keepdims=True) + 1e-12
    # ---- VVD
    vvd = bytearray(m.vvd)
    raw = np.frombuffer(vvd, dtype=np.uint8, count=m.nraw * 48, offset=m.vvd_vstart).reshape(m.nraw, 48).copy()
    raw[:, 16:28] = newP.astype("<f4").view(np.uint8).reshape(m.nraw, 12)
    raw[:, 28:40] = newN.astype("<f4").view(np.uint8).reshape(m.nraw, 12)
    vvd[m.vvd_vstart:m.vvd_vstart + m.nraw * 48] = raw.tobytes()
    if m.raw_tan is not None:
        tan = m.raw_tan.copy()
        tx = np.einsum("nij,nj->ni", J, tan[:, :3])
        tx /= np.linalg.norm(tx, axis=1, keepdims=True) + 1e-12
        # re-orthogonalise against the new normal (Gram-Schmidt), keep handedness in w
        tx -= newN * np.sum(tx * newN, axis=1, keepdims=True)
        tx /= np.linalg.norm(tx, axis=1, keepdims=True) + 1e-12
        tan[:, :3] = tx
        vvd[m.vvd_tstart:m.vvd_tstart + m.nraw * 16] = tan.astype("<f4").tobytes()
    # ---- MDL
    b = bytearray(m.mdl)
    name = rel[len("models/"):] if rel.startswith("models/") else rel
    name = name.replace("/", "\\")
    assert len(name) < 64, "model name too long"
    b[12:76] = name.encode("latin-1").ljust(64, b"\0")
    newbounds = np.array([newP.min(0), newP.max(0)])
    hull = grow_bbox(m.hull, D, newbounds)
    put(b, 104, "<6f", *hull.ravel())
    if np.any(m.view_bb):
        put(b, 128, "<6f", *grow_bbox(m.view_bb, D, newbounds).ravel())
    for so in m.seq_offsets:
        bb = np.array(struct.unpack_from("<6f", b, so + 32)).reshape(2, 3)
        put(b, so + 32, "<6f", *grow_bbox(bb, D, newbounds).ravel())
    for hb in m.hitboxes:  # hitboxes are bone-local: deform in model space and map back
        Wk = W[hb["bone"]]
        cs = bbox_corners(hb["bb"])
        ms = (Wk[:3, :3] @ cs.T).T + Wk[:3, 3]
        dm = D(ms)
        loc = (np.linalg.inv(Wk)[:3, :3] @ dm.T).T + np.linalg.inv(Wk)[:3, 3]
        allp = np.vstack([cs, loc])
        put(b, hb["off"] + 8, "<6f", *allp.min(0), *allp.max(0))
    moved = {}
    for at in m.attachments:
        Wk = W[at["bone"]]
        mpos = (Wk @ at["local"])[:3, 3]
        if not MOVABLE_ATTACH.search(at["name"]):
            moved[at["name"]] = [mpos.round(3).tolist(), mpos.round(3).tolist()]
            continue                              # hand / weapon_bone style attachments never move
        npos = mpos + attach_weight(mpos, P, wprot) * (D(mpos)[0] - mpos)
        lpos = (np.linalg.inv(Wk) @ np.append(npos, 1))[:3]
        put(b, at["off"] + 12 + 12, "<f", lpos[0])   # matrix3x4 row-major: m[0][3]
        put(b, at["off"] + 12 + 28, "<f", lpos[1])   # m[1][3]
        put(b, at["off"] + 12 + 44, "<f", lpos[2])   # m[2][3]
        moved[at["name"]] = [mpos.round(3).tolist(), npos.round(3).tolist()]
    for bp in m.bodyparts:
        for md in bp["models"]:
            idx = np.arange(md["vstart"], md["vstart"] + md["nverts"])
            idx = idx[idx < m.nraw]
            if len(idx):
                r = float(np.linalg.norm(newP[idx], axis=1).max())
                put(b, md["off"] + 68, "<f", max(md["radius"], r))
            for me in md["meshes"]:
                c = np.array(struct.unpack_from("<3f", b, me["off"] + 36))
                put(b, me["off"] + 36, "<3f", *D(c)[0])
    # prepend a cdmaterials directory: append string + new offset table at EOF
    md_dir = matdir.replace("/", "\\").rstrip("\\") + "\\"
    if md_dir.lower().startswith("materials\\"):
        md_dir = md_dir[len("materials\\"):]
    ncd, cdi = S.i32(b, 212), S.i32(b, 216)
    old = [S.i32(b, cdi + 4 * k) for k in range(ncd)]
    while len(b) % 4:
        b.append(0)
    soff = len(b)
    b += md_dir.encode("latin-1") + b"\0"
    while len(b) % 4:
        b.append(0)
    toff = len(b)
    b += struct.pack("<%di" % (ncd + 1), soff, *old)
    put(b, 212, "<i", ncd + 1)
    put(b, 216, "<i", toff)
    put(b, 76, "<i", len(b))
    # ---- write
    dst = os.path.join(out_root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(bytes(b))
    open(dst[:-4] + ".vvd", "wb").write(bytes(vvd))
    for ext in (".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".vtx", ".phy"):
        s = src[:-4] + ext
        if os.path.exists(s):
            shutil.copyfile(s, dst[:-4] + ext)
    return dict(src=src, dst=dst, axis=axis.round(4).tolist(), t_range=[float(t.min()), float(t.max())],
                old_bounds=[P.min(0).round(3).tolist(), P.max(0).round(3).tolist()],
                new_bounds=newbounds.round(3).tolist(), hull=hull.round(3).tolist(),
                attachments=moved, cdmaterials_added=md_dir, params=params, parts=comp_info, protection=prot_info, coarse_parts=coarse_parts,
                density="coarse" if coarse_parts else "dense")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out_root")
    ap.add_argument("rel")
    ap.add_argument("--matdir", required=True)
    ap.add_argument("--params", help="json file with stretch/pivot/bulge/bulge_at/bulge_width/bend")
    for k in ("stretch", "pivot", "bulge", "bulge_at", "bulge_width", "bend"):
        ap.add_argument("--" + k.replace("_", "-"), type=float)
    a = ap.parse_args()
    params = json.load(open(a.params)) if a.params else {}
    for k in ("stretch", "pivot", "bulge", "bulge_at", "bulge_width", "bend"):
        if getattr(a, k) is not None:
            params[k] = getattr(a, k)
    print(json.dumps(mutate(a.src, a.out_root, a.rel, a.matdir, params), indent=1))


if __name__ == "__main__":
    main()
