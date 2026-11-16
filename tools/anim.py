"""Frame 0 of a sequence from a compiled Source model (MDL v48 local animations), read-only.

pose(model, seq_name_or_activity) -> list of 4x4 bone-to-model matrices for that frame
Decodes mstudioanim_t tracks: RAWROT (Quaternion48), RAWROT2 (Quaternion64), RAWPOS (Vector48),
ANIMROT / ANIMPOS (run-length mstudioanimvalue_t, frame 0 = first value), DELTA. Bones without a
track keep their rest pose. Animations in external .ani blocks fall back to the rest pose.
"""
import struct

import numpy as np

import srcmodel as S

RAWPOS, RAWROT, ANIMPOS, ANIMROT, DELTA, RAWROT2 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20


def _i(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _cstr(b, o):
    return b[o:b.find(b"\0", o)].decode("latin-1")


def euler_quat(x, y, z):
    sr, cr = np.sin(x / 2), np.cos(x / 2)
    sp, cp = np.sin(y / 2), np.cos(y / 2)
    sy, cy = np.sin(z / 2), np.cos(z / 2)
    return np.array([sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                     cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy])


def q48(b, o):
    x, y, zw = struct.unpack_from("<HHH", b, o)
    z, wneg = zw & 0x7FFF, zw >> 15
    qx, qy, qz = (x - 32768) / 32768.0, (y - 32768) / 32768.0, (z - 16384) / 16384.0
    w = np.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return np.array([qx, qy, qz, -w if wneg else w])


def q64(b, o):
    v = struct.unpack_from("<Q", b, o)[0]
    x, y, z, wneg = v & 0x1FFFFF, (v >> 21) & 0x1FFFFF, (v >> 42) & 0x1FFFFF, v >> 63
    qx, qy, qz = (x - 1048576) / 1048576.5, (y - 1048576) / 1048576.5, (z - 1048576) / 1048576.5
    w = np.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return np.array([qx, qy, qz, -w if wneg else w])


def v48(b, o):
    return np.array(struct.unpack_from("<3e", b, o), dtype=float)


def animvalue0(b, base, off):
    """Frame-0 value of an mstudioanimvalue_t run (offset 0 means 'no data' -> 0)."""
    if off == 0:
        return 0.0
    p = base + off
    valid, total = b[p], b[p + 1]
    if valid == 0:
        return 0.0
    return float(struct.unpack_from("<h", b, p + 2)[0])


def find_sequence(m, want=("ACT_VM_IDLE", "idle")):
    b = m.mdl
    for w in want:
        for so in m.seq_offsets:
            label = _cstr(b, so + _i(b, so + 4))
            act = _cstr(b, so + _i(b, so + 8))
            if act.upper() == w.upper() or label.lower() == w.lower():
                return so
    for so in m.seq_offsets:
        if "idle" in _cstr(b, so + _i(b, so + 4)).lower():
            return so
    return m.seq_offsets[0] if m.seq_offsets else None


def pose(m, want=("ACT_VM_IDLE", "idle")):
    b = m.mdl
    nb, bi = _i(b, 156), _i(b, 160)
    pos = [bo["pos"].copy() for bo in m.bones]
    quat = [bo["quat"].copy() for bo in m.bones]
    so = find_sequence(m, want)
    if so is not None:
        aidx = struct.unpack_from("<h", b, so + _i(b, so + 60))[0]
        ad = _i(b, 184) + aidx * 100
        animblock, animindex, sidx, sframes = _i(b, ad + 52), _i(b, ad + 56), _i(b, ad + 80), _i(b, ad + 84)
        if sframes:
            animblock, animindex = _i(b, ad + sidx), _i(b, ad + sidx + 4)
        if animblock == 0 and animindex:
            p = ad + animindex
            for _ in range(nb + 1):
                bone, flags = b[p], b[p + 1]
                nxt = struct.unpack_from("<h", b, p + 2)[0]
                if bone < nb:
                    bo = bi + bone * S.BONE_SIZE
                    rest_rot = np.array(struct.unpack_from("<3f", b, bo + 60))
                    posscale = np.array(struct.unpack_from("<3f", b, bo + 72))
                    rotscale = np.array(struct.unpack_from("<3f", b, bo + 84))
                    o = p + 4
                    if flags & RAWROT2:
                        quat[bone] = q64(b, o)
                        o += 8
                    if flags & RAWROT:
                        quat[bone] = q48(b, o)
                        o += 6
                    if flags & ANIMROT:
                        offs = struct.unpack_from("<3h", b, o)
                        e = np.array([animvalue0(b, o, offs[k]) * rotscale[k] for k in range(3)])
                        if not flags & DELTA:
                            e = e + rest_rot
                        quat[bone] = euler_quat(*e)
                        o += 6
                    if flags & RAWPOS:
                        pos[bone] = v48(b, o)
                    elif flags & ANIMPOS:
                        offs = struct.unpack_from("<3h", b, o)
                        d = np.array([animvalue0(b, o, offs[k]) * posscale[k] for k in range(3)])
                        pos[bone] = d if flags & DELTA else d + m.bones[bone]["pos"]
                if nxt == 0:
                    break
                p += nxt
    W = []
    for k, bo in enumerate(m.bones):
        L = np.eye(4)
        L[:3, :3] = S.quat_to_mat(quat[k] / (np.linalg.norm(quat[k]) or 1))
        L[:3, 3] = pos[k]
        W.append(L if bo["parent"] < 0 else W[bo["parent"]] @ L)
    return W
