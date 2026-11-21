"""Random weapon sounds for CustomSlop, from game content every TF2C client already has
(TF2C assets, TF2 and HL2 sound VPKs: nothing has to be downloaded).

index()  -> analysis/sound_index.json (path, source, category) built from the VPK directories
pick(rng, role, vfs) -> a validated wave path for a sound role, or None
Weights: weapon sounds ~70%, other effects (impacts, physics, items, misc, ui, player,
ambient one-shots) ~23%, voice lines (TF2/TF2C/HL2, incl. HL2 citizens and Combine) ~7%.
Excluded: music/, looping waves (smpl loops or cue points where a one-shot is needed), files
longer than the role allows, mp3 (length/peak can't be checked cheaply), and loud files
(peak at full scale on > 0.5% of samples, or RMS above -10 dBFS: earrape-prone).
Soundscripts are written as customslop.<defindex>.<role> into custom_level_sounds.txt.
"""
import io
import json
import math
import os
import re
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vfs as VFS  # noqa: E402

SOURCES = [
    ("tf2c", os.path.join(VFS.TF2C, "vpks", "tf2c_assets_dir.vpk")),
    ("tf2", os.path.join(VFS.TF2_CLIENT, "tf", "tf2_sound_misc_dir.vpk")),
    ("tf2", os.path.join(VFS.TF2_CLIENT, "tf", "tf2_sound_vo_english_dir.vpk")),
    ("hl2", os.path.join(VFS.TF2_CLIENT, "hl2", "hl2_sound_misc_dir.vpk")),
    ("hl2", os.path.join(VFS.TF2_CLIENT, "hl2", "hl2_sound_vo_english_dir.vpk")),
]
INDEX = os.path.join(ROOT, "analysis", "sound_index.json")
BLACKLIST = os.path.join(ROOT, "config", "sound_blacklist.local.txt")
ROLE_MAX_SECONDS = {"single_shot": 2.5, "burst": 2.5, "empty": 1.5, "reload": 4.0, "deploy": 2.0,
                    "melee_miss": 1.5, "melee_hit": 2.0, "melee_hit_world": 2.0}
CAT_WEIGHT = {"weapon": 0.70, "other": 0.23, "voice": 0.07}


def category(path):
    p = path.lower()
    if p.startswith(("sound/music/", "sound/ui/gamestartup", "sound/misc/your_team", "sound/ambient/music")):
        return None
    if "/vo/" in p or p.startswith(("sound/vo/", "sound/npc/")):
        return "voice"
    if p.startswith(("sound/weapons/", "sound/items/", "sound/physics/impact")) and "weapons" in p:
        return "weapon"
    if p.startswith("sound/weapons/"):
        return "weapon"
    return "other"


def index():
    rows = []
    for src, p in SOURCES:
        if not os.path.exists(p):
            continue
        v = VFS.VPK(p)
        for path, (arc, off, ln, pd) in v.ents.items():
            if path.startswith("sound/") and path.endswith(".wav"):
                c = category(path)
                if c:
                    rows.append(dict(path=path, src=src, cat=c, bytes=ln + len(pd), vpk=p))
    json.dump(rows, open(INDEX, "w"))
    return rows


def wav_check(data, role):
    """-> (ok, info). Parses RIFF chunks: fmt, data, smpl (loops), cue."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, "not RIFF/WAVE"
    o, fmt, pcm, loops, cue = 12, None, None, 0, False
    while o + 8 <= len(data):
        cid, sz = data[o:o + 4], struct.unpack_from("<I", data, o + 4)[0]
        body = data[o + 8:o + 8 + sz]
        if cid == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", body, 0)
        elif cid == b"data":
            pcm = body
        elif cid == b"smpl" and len(body) >= 36:
            loops = struct.unpack_from("<I", body, 28)[0]
        elif cid == b"cue ":
            cue = True
        o += 8 + sz + (sz & 1)
    if not fmt or pcm is None:
        return False, "no fmt/data"
    tag, ch, rate, brate, align, bits = fmt
    if tag not in (1, 2) or rate <= 0 or brate <= 0:
        return False, "format %d" % tag
    secs = len(pcm) / brate
    if loops or cue:
        return False, "looping wave"
    if secs > ROLE_MAX_SECONDS.get(role, 3.0) or secs < 0.05:
        return False, "length %.2fs" % secs
    info = dict(seconds=round(secs, 2), rate=rate, bits=bits, channels=ch)
    if tag == 1 and bits == 16:
        a = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if len(a):
            clip = float(np.mean(np.abs(a) > 0.995))
            rms = 20 * math.log10(float(np.sqrt(np.mean(a * a))) + 1e-9)
            info.update(clip=round(clip, 4), rms_db=round(rms, 1))
            if clip > 0.005 or rms > -10:
                return False, "too loud (clip %.3f, rms %.1f dB)" % (clip, rms)
    elif tag == 1 and bits == 8:
        a = (np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) - 128) / 128
        rms = 20 * math.log10(float(np.sqrt(np.mean(a * a))) + 1e-9) if len(a) else -99
        info.update(rms_db=round(rms, 1))
        if rms > -10:
            return False, "too loud"
    return True, info


class Picker:
    def __init__(self):
        rows = json.load(open(INDEX)) if os.path.exists(INDEX) else index()
        self.by = {}
        for r in rows:
            self.by.setdefault(r["cat"], []).append(r)
        self.vpks = {}
        self.rejected = []
        # Optional local-only blacklist (one wave path per line, '#' comments), never committed: an
        # operator's own "never pick this sound again" list (config/sound_blacklist.local.txt is gitignored).
        self.blacklist = set()
        if os.path.exists(BLACKLIST):
            for ln in open(BLACKLIST, encoding="utf-8"):
                ln = ln.split("#", 1)[0].strip().lower().replace("\\", "/")
                if ln:
                    self.blacklist.add(ln[len("sound/"):] if ln.startswith("sound/") else ln)

    def _read(self, r):
        v = self.vpks.get(r["vpk"]) or self.vpks.setdefault(r["vpk"], VFS.VPK(r["vpk"]))
        return v.read(r["path"])

    def pick(self, rng, role, tries=40):
        for _ in range(tries):
            cat = rng.choices(list(CAT_WEIGHT), weights=list(CAT_WEIGHT.values()))[0]
            pool = self.by.get(cat) or []
            if role.startswith("melee") and cat == "weapon":
                pool = [r for r in pool if re.search(r"(melee|hit|swing|bat|axe|knife|wrench|bottle|fist|shovel|bonesaw|cbar|crowbar)", r["path"])] or pool
            if role == "reload" and cat == "weapon":
                pool = [r for r in pool if "reload" in r["path"] or "clip" in r["path"] or "load" in r["path"]] or pool
            if not pool:
                continue
            r = rng.choice(pool)
            if r["path"][len("sound/"):].lower() in self.blacklist:
                continue
            data = self._read(r)
            if data is None:
                continue
            ok, info = wav_check(data, role)
            if ok:
                return dict(wave=r["path"][len("sound/"):], src=r["src"], cat=cat, **info)
            self.rejected.append((r["path"], info))
        return None


def soundscript(name, pick, role):
    chan = "CHAN_WEAPON" if role in ("single_shot", "burst", "empty") else "CHAN_STATIC" if role == "reload" else "CHAN_ITEM"
    return ('"%s"\n{\n\t"channel"\t"%s"\n\t"volume"\t"0.85"\n\t"soundlevel"\t"SNDLVL_80dB"\n\t"pitch"\t"PITCH_NORM"\n'
            '\t"wave"\t")%s"\n}\n' % (name, chan, pick["wave"]))


if __name__ == "__main__":
    rows = index()
    import collections
    print(len(rows), collections.Counter((r["src"], r["cat"]) for r in rows))
