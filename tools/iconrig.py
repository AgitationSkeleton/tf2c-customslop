"""What an icon shows besides the bare weapon mesh, per donor (stored in the donor's camera fit):

  f["model_kind"]  "w" world model | "v" view model in its idle pose
  f["arms"]        view-model arms bonemerged onto the posed view model, e.g.
                   "models/weapons/c_models/c_heavy_arms.mdl" (TF2C's Chekhov's Punch / Shock Therapy
                   icons show the class's arms; OF's Berserk bucket shows the Merc's arms)
  f["bind_pose"]   view model rendered unposed (its world-model geometry), f["squeeze"]: gloves
                   moved toward each other (tf2cc's Hammerfists icon pose)
  f["hide"]        mesh parts the original icon does not show: substrings of material names or of
                   the bone a vertex is skinned to (e.g. "shell" - the loose shotgun shell of beta 4
                   view models)

Used identically for fitting the donor's camera, the audit, and rendering a mutated weapon
(iconfit.render_icon applies with_arms/hide), so a CustomSlop weapon's icon has the same parts as
its donor's original icon.
"""
import copy
import os
import re
import tempfile

import numpy as np

import srcmodel as S

_FS = None


def fs():
    global _FS
    if _FS is None:
        import vfs as VFS
        _FS = VFS.VFS()
    return _FS


def load_icon_model(ctx, d, f):
    """(model, textures, materials) of donor d as fit f wants it (unmutated donor)."""
    import iconfit as IF
    import pipeline
    import vmrender
    kind = (f or {}).get("model_kind", "w")
    rel = f.get("model") if f and f.get("model") else (d["mp"] if kind == "v" or not d.get("mw") else d["mw"])
    tmp = tempfile.mkdtemp(dir=os.path.join(pipeline.ROOT, "tmp"))
    m = S.load(pipeline.extract_model(ctx, rel, tmp))
    if kind == "v" or os.path.basename(rel).lower().startswith("v_"):
        m = IF.posed(m)
    tex = vmrender.textures_for(ctx, m, None)
    mats = vmrender.materials_for(ctx, m, None)
    return m, tex, mats


def hide(m, words):
    """Copy of m without the triangles whose material or skinned bone name contains any word."""
    if not words:
        return m
    words = [w.lower() for w in words]
    bad_bone = np.array([any(w in b["name"].lower() for w in words) for b in m.bones] or [False], bool)
    vb = np.zeros(len(m.raw_pos), bool)
    if len(m.bones):
        for j in range(m.raw_bones.shape[1]):
            vb |= (m.raw_nb > j) & bad_bone[np.clip(m.raw_bones[:, j], 0, len(m.bones) - 1)] & (m.raw_weights[:, j] > 0.5)
    skin = m.skins[0] if m.skins else list(range(len(m.textures)))
    tris, bgs = [], []
    bg = getattr(m, "tri_bodygroup", None)
    for i, (mat, t) in enumerate(m.tris):
        ti = skin[mat] if mat < len(skin) else mat
        tname = m.textures[ti].lower() if ti < len(m.textures) else ""
        if any(w in tname for w in words):
            continue
        keep = ~(vb[t[:, 0]] & vb[t[:, 1]] & vb[t[:, 2]])
        if keep.any():
            tris.append((mat, t[keep]))
            bgs.append(bg[i] if bg is not None and i < len(bg) else (0, 0))
    m2 = copy.copy(m)
    m2.tris = tris
    m2.tri_bodygroup = bgs if bg is not None else None
    return m2


class _Merged:
    """Minimal model object (what iconfit.raster_buffers / tri_list read) for weapon + arms."""

    def __init__(self, parts):
        self.raw_pos = np.vstack([p[0] for p in parts])
        self.raw_nrm = np.vstack([p[1] for p in parts])
        self.raw_uv = np.vstack([p[2] for p in parts])
        self.tris, self.textures, self.cdmaterials = [], [], []
        off_v, off_t = 0, 0
        for P, _, _, tris, ntex in parts:
            for mat, t in tris:
                self.tris.append((mat + off_t, t + off_v))
            off_v += len(P)
            off_t += ntex
        self.skins = [list(range(off_t))]
        self.bodyparts = [dict(models=[dict(vstart=0, nverts=len(self.raw_pos))])]
        self.bones, self.attachments = [], []


def _skin_tris(m):
    """(material index after skin 0, triangles) of m's default bodygroups."""
    import iconfit as IF
    return IF.tri_list(m)


def with_arms(m, tex, mats, arms_rel, files_tex=None):
    """Posed view model m (iconfit.posed copy, bones intact) + the arms model bonemerged onto it."""
    import anim
    import vfs as VFS  # noqa: F401
    import vmrender
    import vtf
    raw = fs().read(arms_rel)
    if raw is None:
        return m, tex, mats
    tmp = tempfile.mkdtemp()
    base = os.path.join(tmp, os.path.basename(arms_rel))
    for ext in (".mdl", ".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".vtx"):
        r_ = fs().read(arms_rel[:-4] + ext)
        if r_ is not None:
            open(base[:-4] + ext, "wb").write(r_)
    arms = S.load(base)
    W = anim.pose(m)
    names = {b["name"]: k for k, b in enumerate(m.bones)}
    AW = vmrender.bonemerge(arms, names, W)
    AP, AN = vmrender.skinned(arms, AW)

    class _C:                                  # textures_for / materials_for need ctx.fs
        pass
    c = _C()
    c.fs = fs()
    atex = vmrender.textures_for(c, arms, None)
    amats = vmrender.materials_for(c, arms, None)
    wt = _skin_tris(m)
    at = _skin_tris(arms)
    nt_w = max([ti for ti, _ in wt] + [len(m.textures) - 1]) + 1
    nt_a = max([ti for ti, _ in at] + [len(arms.textures) - 1]) + 1
    mm = _Merged([(m.raw_pos, m.raw_nrm, m.raw_uv, wt, nt_w), (AP, AN, arms.raw_uv, at, nt_a)])
    tex2 = dict(tex or {})
    mats2 = dict(mats or {})
    for k in range(nt_a):
        tex2[nt_w + k] = (atex or {}).get(k)
        mats2[nt_w + k] = (amats or {}).get(k, {})
    mm.textures = list(m.textures) + [""] * (nt_w - len(m.textures)) + list(arms.textures)
    del vtf
    return mm, tex2, mats2


def apply(m, tex, mats, f):
    """The donor's icon parts (fit f) applied to model m (donor or mutated copy)."""
    if not f:
        return m, tex, mats
    if f.get("bind_pose") and getattr(m, "bind_pos", None) is not None:
        # the view model's bind pose = the world model's geometry (tf2cc's w_hammerfists_b4 is the
        # Hammerfists view-model mesh unposed): render it unposed, as tf2cc's icon was
        m = copy.copy(m)
        m.raw_pos, m.raw_nrm = m.bind_pos, m.bind_nrm
    if f.get("squeeze"):
        # tf2cc's pose: each half (x < 0 / x >= 0, one glove each) moved this many units toward the
        # other - a translation, no mirroring
        m = copy.copy(m)
        P = m.raw_pos.copy()
        P[:, 0] -= np.sign(P[:, 0]) * float(f["squeeze"])
        m.raw_pos = P
    if f.get("hide"):
        m = hide(m, f["hide"])
    if f.get("arms") and getattr(m, "bones", None):
        try:
            m, tex, mats = with_arms(m, tex, mats, f["arms"])
        except Exception:                      # never fail a weapon over its icon's arms
            pass
    return m, tex, mats


def nocull(mats, ti):
    return bool(((mats or {}).get(ti) or {}).get("nocull"))


def is_translucent(mats, ti):
    return bool(((mats or {}).get(ti) or {}).get("translucent"))


def alphatest(mats, ti):
    mt = (mats or {}).get(ti) or {}
    return float(mt.get("alphatestref") or 0.5) if mt.get("alphatest") else None


_ = re
