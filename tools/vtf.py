"""Minimal VTF reader/writer for CustomSlop research (read-only on inputs).

decode(data) -> (width, height, numpy uint8 RGBA array of the top mip, info dict)
encode_bgra8888(rgba, mips=True) -> VTF 7.2 bytes (uncompressed BGRA8888, the format TF2C's
                                    256x256 loadout icons use; no DXT encoder needed)
CLI: python -I vtf.py <in.vtf> <out.png>
"""
import struct
import sys

import numpy as np

FMT_BPP = {0: 4, 1: 4, 2: 3, 3: 3, 4: 2, 12: 4, 16: 4}  # RGBA8888 ABGR8888 RGB888 BGR888 RGB565 BGRA8888 BGRX8888
BLOCK = {13: 8, 14: 16, 15: 16}


def _mip_size(w, h, fmt):
    if fmt in BLOCK:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK[fmt]
    return w * h * FMT_BPP[fmt]


def _rgb565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.array([r, g, b], dtype=np.int32)


def _decode_dxt(buf, w, h, fmt):
    out = np.zeros((max(h, 4), max(w, 4), 4), dtype=np.uint8)
    bs = BLOCK[fmt]
    o = 0
    for by in range(0, max(h, 4), 4):
        for bx in range(0, max(w, 4), 4):
            alpha = np.full(16, 255, dtype=np.int32)
            if fmt == 15:
                a0, a1 = buf[o], buf[o + 1]
                bits = int.from_bytes(buf[o + 2:o + 8], "little")
                pal = [a0, a1]
                if a0 > a1:
                    pal += [((6 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
                else:
                    pal += [((4 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
                alpha = np.array([pal[(bits >> (3 * i)) & 7] for i in range(16)])
                co = o + 8
            elif fmt == 14:
                bits = int.from_bytes(buf[o:o + 8], "little")
                alpha = np.array([((bits >> (4 * i)) & 15) * 17 for i in range(16)])
                co = o + 8
            else:
                co = o
            c0, c1, idx = struct.unpack_from("<HHI", buf, co)
            p0, p1 = _rgb565(c0), _rgb565(c1)
            if c0 > c1 or fmt != 13:
                cols = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
                tr = False
            else:
                cols = [p0, p1, (p0 + p1) // 2, np.zeros(3, np.int32)]
                tr = True
            for i in range(16):
                ci = (idx >> (2 * i)) & 3
                y, x = by + i // 4, bx + i % 4
                out[y, x, :3] = cols[ci]
                out[y, x, 3] = 0 if (tr and ci == 3) else alpha[i]
            o += bs
    return out[:h, :w]


def decode(data):
    sig, v0, v1, hsize, w, h, flags, frames, first = struct.unpack_from("<4sIIIHHIHH", data, 0)
    assert sig == b"VTF\0", "not a VTF"
    fmt, mips, lfmt, lw, lh = struct.unpack_from("<iBiBB", data, 0x34)
    # top mip is stored last; skip low-res thumbnail and smaller mips
    off = hsize + (_mip_size(lw, lh, lfmt) if lfmt != -1 else 0)
    if (v0, v1) >= (7, 3):
        nres = struct.unpack_from("<I", data, 0x44)[0]
        for i in range(nres):
            tag, rflags, roff = struct.unpack_from("<3sBI", data, 0x50 + 8 * i)
            if tag == b"\x30\0\0":
                off = roff
    for m in range(mips - 1, 0, -1):
        off += _mip_size(max(1, w >> m), max(1, h >> m), fmt) * frames
    buf = data[off:off + _mip_size(w, h, fmt)]
    if fmt in BLOCK:
        img = _decode_dxt(buf, w, h, fmt)
    else:
        a = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, FMT_BPP[fmt])
        if fmt == 0:
            img = a.copy()
        elif fmt == 1:
            img = a[:, :, [3, 2, 1, 0]].copy()
        elif fmt == 12:
            img = a[:, :, [2, 1, 0, 3]].copy()
        elif fmt == 16:
            img = a[:, :, [2, 1, 0, 3]].copy(); img[:, :, 3] = 255
        elif fmt in (2, 3):
            rgb = a if fmt == 2 else a[:, :, ::-1]
            img = np.dstack([rgb, np.full((h, w), 255, np.uint8)])
        else:
            raise ValueError("format %d not handled" % fmt)
    return w, h, img, dict(fmt=fmt, mips=mips, flags=flags, version="%d.%d" % (v0, v1), frames=frames)


def encode_bgra8888(rgba, mips=True, flags=0x2000 | 0x4 | 0x8):
    """rgba: HxWx4 uint8, power-of-two sides. flags default: EIGHTBITALPHA|CLAMPS|CLAMPT."""
    from PIL import Image
    h, w = rgba.shape[:2]
    levels = [rgba]
    if mips:
        im = Image.fromarray(rgba, "RGBA")
        while min(levels[-1].shape[:2]) > 1:
            nw, nh = max(1, levels[-1].shape[1] // 2), max(1, levels[-1].shape[0] // 2)
            levels.append(np.asarray(im.resize((nw, nh), Image.LANCZOS)))
    hsize = 80
    hdr = struct.pack("<4sIIIHHIHH4x3f4xfiBiBBH", b"VTF\0", 7, 2, hsize, w, h, flags, 1, 0,
                      0.5, 0.5, 0.5, 1.0, 12, len(levels), -1, 0, 0, 1)
    hdr = hdr.ljust(hsize, b"\0")
    body = b"".join(lv[:, :, [2, 1, 0, 3]].tobytes() for lv in reversed(levels))
    return hdr + body


if __name__ == "__main__":
    from PIL import Image
    w, h, img, info = decode(open(sys.argv[1], "rb").read())
    Image.fromarray(img, "RGBA").save(sys.argv[2])
    print(w, h, info)


def _dxt_blocks(rgba, fmt):
    """Encode one mip level to DXT1 (13) / DXT5 (15) block data with Pillow's DDS writer."""
    import io
    from PIL import Image
    h, w = rgba.shape[:2]
    pad = np.zeros((max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4), 4), np.uint8)
    pad[:h, :w] = rgba
    bio = io.BytesIO()
    Image.fromarray(pad, "RGBA").save(bio, format="DDS", pixel_format="DXT1" if fmt == 13 else "DXT5")
    d = bio.getvalue()
    hdr = 128 + (20 if d[84:88] == b"DX10" else 0)
    need = _mip_size(w, h, fmt)
    blocks = d[hdr:hdr + need]
    assert len(blocks) == need, (len(blocks), need)
    return blocks


def encode(rgba, fmt=15, mips=True, flags=0x2000 | 0x4 | 0x8, resample=None):
    """Encode HxWx4 uint8 RGBA as a VTF 7.2: fmt 12 = BGRA8888, 13 = DXT1, 15 = DXT5.
    resample(rgba, (w, h)) -> rgba builds the mip chain (default: straight-alpha Lanczos)."""
    from PIL import Image
    h, w = rgba.shape[:2]
    levels = [rgba]
    if mips:
        im = Image.fromarray(rgba, "RGBA")
        while max(levels[-1].shape[:2]) > 1:
            nw, nh = max(1, levels[-1].shape[1] // 2), max(1, levels[-1].shape[0] // 2)
            levels.append(resample(rgba, (nw, nh)) if resample else np.asarray(im.resize((nw, nh), Image.LANCZOS)))
    if fmt == 13:
        flags &= ~0x2000
        flags |= 0x100 if rgba[:, :, 3].min() < 255 else 0   # ONEBITALPHA when holes exist
    hsize = 80
    hdr = struct.pack("<4sIIIHHIHH4x3f4xfiBiBBH", b"VTF" + bytes(1), 7, 2, hsize, w, h, flags, 1, 0,
                      0.5, 0.5, 0.5, 1.0, fmt, len(levels), -1, 0, 0, 1)
    hdr = hdr.ljust(hsize, bytes(1))
    parts = []
    for lv in reversed(levels):
        if fmt == 12:
            parts.append(lv[:, :, [2, 1, 0, 3]].tobytes())
        else:
            parts.append(_dxt_blocks(lv, fmt))
    return hdr + b"".join(parts)
