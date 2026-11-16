"""Build the CustomSlop attribute catalogue (read-only inputs).

Joins:
  1. TF2C base schema attribute definitions (name, attribute_class, description_format,
     effect_type, hidden, stored_as_integer)                     -> what the schema accepts
  2. CALL_ATTRIB_HOOK_* sites in the 2024 TF2C source tree      -> where the class is read and
     which weapon source files read it (a proxy for "which item classes honour it")
  3. presence of the attribute_class string in TF2C 5205 server.dll / client.dll strings
     (the hook macros embed the class name as a literal)        -> still read on build 5205
Output: analysis/attributes_5205.json and analysis/attributes_5205.tsv
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths as P  # noqa: E402
import kv  # noqa: E402

SRC = P.opt("tf2c_source_dir")
SCHEMA = P.data("items_game.txt")
SV = P.data("server_strings.txt")
CL = P.data("client_strings.txt")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis")

root = kv.load(SCHEMA)[0].get("items_game")
defs = []
for k, a in root.get("attributes").blocks():
    defs.append(dict(id=int(k), name=a.get("name"), cls=a.get("attribute_class"),
                     fmt=a.get("description_format"), effect=a.get("effect_type"),
                     hidden=a.get("hidden") == "1", integer=a.get("stored_as_integer") == "1",
                     desc=a.get("description_string"), type=a.get("attribute_type")))

hook = re.compile(r"CALL_ATTRIB_HOOK_([A-Z_]+)\s*\(\s*([^;]*?)\)\s*;", re.S)
sites = collections.defaultdict(set)
kinds = collections.defaultdict(set)
for dp, _, fs in (os.walk(SRC) if SRC else []):
    for f in fs:
        if not f.endswith((".cpp", ".h")):
            continue
        t = open(os.path.join(dp, f), encoding="latin-1").read()
        for mm in hook.finditer(t):
            args = [x.strip() for x in mm.group(2).split(",")]
            cls = args[-1]
            if re.fullmatch(r"[a-z0-9_]+", cls):
                sites[cls].add(f)
                kinds[cls].add(mm.group(1))

sv = set(open(SV, encoding="latin-1", errors="replace").read().split("\n"))
cl = set(open(CL, encoding="latin-1", errors="replace").read().split("\n"))

rows = []
for d in defs:
    c = d["cls"]
    files = sorted(sites.get(c, []))
    weap = sorted({re.sub(r"\.(cpp|h)$", "", f) for f in files if f.startswith(("tf_weapon", "tf_projectile", "tf2c_weapon", "tf_weaponbase"))})
    d.update(hooked_2024=bool(files), hook_kinds=sorted(kinds.get(c, [])), files=files, weapon_files=weap,
             in_5205_server=c in sv, in_5205_client=c in cl)
    rows.append(d)
os.makedirs(OUT, exist_ok=True)
json.dump(rows, open(os.path.join(OUT, "attributes_5205.json"), "w"), indent=1)
with open(os.path.join(OUT, "attributes_5205.tsv"), "w", encoding="utf-8") as f:
    f.write("id\tname\tattribute_class\tformat\teffect\thidden\tin_5205_server\tin_5205_client\thook_kinds\tfiles\n")
    for r in rows:
        f.write("\t".join(str(x) for x in (r["id"], r["name"], r["cls"], r["fmt"], r["effect"], int(r["hidden"]),
                                           int(r["in_5205_server"]), int(r["in_5205_client"]),
                                           ",".join(r["hook_kinds"]), ",".join(r["files"]))) + "\n")
n = len(rows)
print("schema attribute defs:", n)
print("attribute classes with a hook site in 2024 source:", sum(r["hooked_2024"] for r in rows))
print("class string present in 5205 server.dll:", sum(r["in_5205_server"] for r in rows))
print("present in 5205 server but not hooked in 2024 source (new in 5205 or indirect):",
      sum(r["in_5205_server"] and not r["hooked_2024"] for r in rows))
print("neither (dead / description-only / TF2-only leftovers):",
      sum(not r["in_5205_server"] and not r["hooked_2024"] for r in rows))
print("formats:", collections.Counter(r["fmt"] for r in rows).most_common())
