"""Localisation tokens (#Attrib_..., #TF_Weapon_...) from the user's own TF2 / TF2C installs.

Read at runtime, never copied or redistributed. Later files override earlier ones:
  1. TF2 tf_english.txt   (Steam TF2 client install, else the TF2 dedicated server's resource/)
  2. TF2C tf_english.txt + tf2classified_english.txt (TF2C server or client resource/)
Paths come from config (customslop.json "loc_files") or auto-discovery.
"""
import glob
import os
import re

import cspaths as P

CANDIDATES = P.loc_files()
_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"')


def _read(path):
    b = open(path, "rb").read()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16")
    return b.decode("utf-8", errors="replace")


class Loc:
    def __init__(self, files=None):
        self.tokens = {}
        self.files = []
        for p in files or CANDIDATES:
            if os.path.exists(p):
                txt = _read(p)
                for k, v in _PAIR.findall(txt):
                    if k.startswith("[$"):
                        continue
                    self.tokens[k.lower()] = v.replace('\\"', '"').replace("\\n", "\n")
                self.files.append(p)

    def get(self, token, default=None):
        if token is None:
            return default
        t = token[1:] if token.startswith("#") else token
        return self.tokens.get(t.lower(), default if default is not None else token)
