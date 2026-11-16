"""Read-only virtual filesystem over the TF2C server's search path (loose dirs + VPKs), in
gameinfo order, so CustomSlop can fetch donor models, materials and icons without extracting
whole VPKs. Nothing is ever written to any source.
"""
import glob
import os
import struct

import cspaths as P

TF2C = P.opt("server_root") or ""
TF2 = P.opt("tf2_server_dir") or ""
# the dedicated server ships only the texture VPK directory, not its archives: textures (rendering
# and recolour sources only) come from the TF2 client install
TF2_CLIENT = P.opt("tf2_client_dir") or ""


def _default_order():
    """The server's own search order: custom/* (alphabetical: loose folders and VPKs), the TF2C
    VPKs, TF2 + HL2 content, the game dir, then optional extra donor folders."""
    order = []
    for p in sorted(glob.glob(os.path.join(TF2C, "custom", "*"))):
        order.append(("vpk", p) if p.endswith(".vpk") else ("dir", p))
    for name in ("tf2c_assets_dir.vpk", "mb2_tf_content_dir.vpk", "mb2_shared_content_dir.vpk", "tf2c_overrides_dir.vpk"):
        order.append(("vpk", os.path.join(TF2C, "vpks", name)))
    order += [("vpk", os.path.join(TF2_CLIENT, "tf", "tf2_textures_dir.vpk")),
              ("vpk", os.path.join(TF2, "tf", "tf2_misc_dir.vpk")),
              ("vpk", os.path.join(TF2_CLIENT, "hl2", "hl2_textures_dir.vpk")),
              ("vpk", os.path.join(TF2, "hl2", "hl2_misc_dir.vpk")),
              ("dir", TF2C)]
    if P.opt("tf2cc_staging_dir"):
        order.append(("dir", P.opt("tf2cc_staging_dir")))
    order += [("dir", d) for d in P.opt("extra_donor_dirs", []) or []]
    # CustomSlop's own installed folder is never a donor source
    return [(k, p) for k, p in order if "customslop" not in os.path.basename(p).lower()]


DEFAULT_ORDER = _default_order()


def _rd(f):
    b = bytearray()
    while True:
        c = f.read(1)
        if c in (b"\0", b""):
            return b.decode("latin-1")
        b += c


class VPK:
    def __init__(self, path):
        self.path = path
        self.ents = {}
        with open(path, "rb") as f:
            sig, ver, tree = struct.unpack("<III", f.read(12))
            if ver == 2:
                f.read(16)
            self.base = 12 + (16 if ver == 2 else 0) + tree
            while True:
                ext = _rd(f)
                if not ext:
                    break
                while True:
                    d = _rd(f)
                    if not d:
                        break
                    while True:
                        n = _rd(f)
                        if not n:
                            break
                        crc, pre, arc, off, ln, term = struct.unpack("<IHHIIH", f.read(18))
                        pd = f.read(pre)
                        p = ((d + "/") if d.strip() else "") + n + "." + ext
                        self.ents[p.lower()] = (arc, off, ln, pd)

    def read(self, p):
        e = self.ents.get(p.lower())
        if not e:
            return None
        arc, off, ln, pd = e
        if not ln:
            return pd
        if arc == 0x7FFF:
            with open(self.path, "rb") as f:
                f.seek(self.base + off)
                return pd + f.read(ln)
        ap = self.path[:-8] + "_%03d.vpk" % arc if self.path.endswith("_dir.vpk") else self.path
        with open(ap, "rb") as f:
            f.seek(off)
            return pd + f.read(ln)


class VFS:
    def __init__(self, order=None):
        self.src = []
        for kind, p in order or DEFAULT_ORDER:
            if kind == "dir" and os.path.isdir(p):
                self.src.append(("dir", p))
            elif kind == "vpk" and os.path.exists(p):
                self.src.append(("vpk", VPK(p)))

    def read(self, rel):
        rel = rel.replace("\\", "/").lstrip("/")
        for kind, s in self.src:
            if kind == "dir":
                fp = os.path.join(s, rel)
                if os.path.exists(fp):
                    return open(fp, "rb").read()
            else:
                d = s.read(rel)
                if d is not None:
                    return d
        return None

    def where(self, rel):
        rel = rel.replace("\\", "/").lstrip("/")
        for kind, s in self.src:
            if kind == "dir" and os.path.exists(os.path.join(s, rel)):
                return s
            if kind == "vpk" and rel.lower() in s.ents:
                return s.path
        return None

    def extract(self, rel, out_root):
        d = self.read(rel)
        if d is None:
            return None
        op = os.path.join(out_root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(op), exist_ok=True)
        open(op, "wb").write(d)
        return op
