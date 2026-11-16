"""Scan a VPK for .mdl files and record their bounding size from the MDL header (hull, falling
back to view bbox), for picking 'silly but not gigantic' projectile models. Read-only.
usage: python -I model_roster.py <x_dir.vpk> <out.json> [prefix ...]"""
import json, os, struct, sys
def rd(f):
    b = b''
    while True:
        c = f.read(1)
        if c in (b'\0', b''): return b.decode('latin1')
        b += c
def entries(p):
    f = open(p, 'rb'); sig, ver, tree = struct.unpack('<III', f.read(12))
    if ver == 2: f.read(16)
    hdr = 12 + (16 if ver == 2 else 0); out = {}
    while True:
        ext = rd(f)
        if not ext: break
        while True:
            d = rd(f)
            if not d: break
            while True:
                n = rd(f)
                if not n: break
                crc, pre, arc, off, ln, term = struct.unpack('<IHHIIH', f.read(18))
                pd = f.read(pre)
                if ext == 'mdl':
                    out[(d + '/' if d != ' ' else '') + n + '.' + ext] = (arc, off, ln, pd)
    return f, hdr + tree, out
vp = sys.argv[1]; f, base, ents = entries(vp)
prefixes = sys.argv[3:] or ['models/']
res = []; handles = {}
for path, (arc, off, ln, pd) in ents.items():
    if not any(path.startswith(p) for p in prefixes): continue
    if arc == 0x7fff: f.seek(base + off); data = pd + f.read(min(ln, 256))
    else:
        ap = vp.replace('_dir.vpk', '_%03d.vpk' % arc)
        h = handles.get(ap) or handles.setdefault(ap, open(ap, 'rb'))
        h.seek(off); data = pd + h.read(min(ln, 256))
    if data[:4] != b'IDST' or len(data) < 160: continue
    hull = struct.unpack_from('<6f', data, 104); vb = struct.unpack_from('<6f', data, 128)
    bb = hull if any(hull) else vb
    size = [bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]]
    nbones = struct.unpack_from('<i', data, 156)[0]
    res.append(dict(path=path, size=[round(s, 1) for s in size], diag=round(sum(s*s for s in size) ** .5, 1), bones=nbones))
json.dump(res, open(sys.argv[2], 'w'))
print(len(res), 'models')
