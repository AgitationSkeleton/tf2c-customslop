"""One-time setup: extract and index what CustomSlop needs from YOUR game installs (read-only).

  python -I tools/setup_data.py
writes into <workdir>/data and <workdir>/analysis:
  data/items_game.txt, data/mvm_upgrades.txt   from the TF2C assets VPK
  data/server_strings.txt, data/client_strings.txt   printable strings of the 5205 binaries
  analysis/attributes_5205.json   (attr_catalog.py)  -> analysis/attribute_pool_5205.json (attrpool.py)
  analysis/tf2_model_roster.json + projectile_model_candidates.json (model_roster.py)
  analysis/sound_index.json (sounds.py)
then run tools/donor_audit.py and (optionally) tools/fit_icons.py --all.
Nothing is copied out of the game except these derived index files.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cspaths as P  # noqa: E402
import vfs  # noqa: E402


def strings_of(path, out, minlen=4):
    data = open(path, "rb").read()
    found = re.findall(rb"[\x20-\x7e]{%d,}" % minlen, data)
    with open(out, "w", encoding="latin-1") as f:
        for s in found:
            f.write(s.decode("latin-1") + "\n")


def main():
    os.makedirs(P.data_dir(), exist_ok=True)
    os.makedirs(os.path.join(P.workdir(), "analysis"), exist_ok=True)
    tf2c_vpk = vfs.VPK(os.path.join(P.server_root(), "vpks", "tf2c_assets_dir.vpk"))
    for rel, name in (("scripts/items/items_game.txt", "items_game.txt"), ("scripts/items/mvm_upgrades.txt", "mvm_upgrades.txt")):
        b = tf2c_vpk.read(rel)
        if b is None:
            raise SystemExit("not found in the TF2C VPK: " + rel)
        open(P.data(name), "wb").write(b)
    strings_of(os.path.join(P.server_root(), "bin", "x64", "server.dll"), P.data("server_strings.txt"))
    cl = os.path.join(P.server_root(), "bin", "x64", "client.dll")
    if os.path.exists(cl):
        strings_of(cl, P.data("client_strings.txt"))
    else:
        open(P.data("client_strings.txt"), "w").close()
    py = sys.executable
    subprocess.run([py, "-I", os.path.join(HERE, "attr_catalog.py")], check=True)
    subprocess.run([py, "-I", os.path.join(HERE, "attrpool.py")], check=True)
    subprocess.run([py, "-I", os.path.join(HERE, "model_roster.py"),
                    os.path.join(P.cfg("tf2_server_dir"), "tf", "tf2_misc_dir.vpk"),
                    os.path.join(P.workdir(), "analysis", "tf2_model_roster.json"), "models/"], check=True)
    roster = json.load(open(os.path.join(P.workdir(), "analysis", "tf2_model_roster.json")))
    skip = ("/player/", "animations", "_arms", "/v_models/", "c_models/c_", "gibs", "/workshop/player", "hwm", "/bots/",
            "/buildables/", "skybox", "/effects/")
    ok = sorted(m["path"] for m in roster if 4 <= m["diag"] <= 40 and not any(x in m["path"] for x in skip))
    json.dump(ok, open(os.path.join(P.workdir(), "analysis", "projectile_model_candidates.json"), "w"), indent=0)
    subprocess.run([py, "-I", os.path.join(HERE, "sounds.py")], check=True)
    print("data ready; next: python -I tools/donor_audit.py")


if __name__ == "__main__":
    main()
