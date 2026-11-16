"""Every machine-specific path CustomSlop uses comes from config/customslop.json (copy
config/customslop.example.json). Nothing here is hard-coded to one machine.

Keys (see the example file for descriptions):
  server_root          the TF2 Classified game dir the live server runs (".../tf2classified")
  tf2_server_dir       TF2 dedicated-server content root (contains tf/ and hl2/ VPK dirs)
  tf2_client_dir       a TF2 client install ("Team Fortress 2" folder): textures, sounds, fonts
  tf2c_client_dir      optional: a TF2 Classified client install (extra localisation)
  steam_dir            optional: Steam root (finds every library for the fonts)
  fonts_dir            optional: folder with tf2build.ttf + tf2secondary.ttf
  extra_donor_dirs     optional list of loose game-path folders searched for donor files
  tf2cc_staging_dir    optional: a staged tf2cc tree (Open Fortress Merc / MarxVee donors)
  oldmerc_dir          optional: tf2cc's old-Merc research folder (oldmerc_items.json + staging/)
  tf2classic_b4_dir    optional: an old TF2 Classic 2.0.0 beta 4 "tf2classic" folder
  tf2c_source_dir      optional: TF2C source "src/game" folder (attribute read-site analysis)
  enginetest_dir       optional: folder with a COPY of srcds binaries for the engine-load test
  workdir              optional: where state/, queue/, cache/, analysis/, data/ live (default: repo)
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.environ.get("CUSTOMSLOP_CONFIG") or os.path.join(ROOT, "config", "customslop.json")
_cache = None


def config():
    global _cache
    if _cache is None:
        _cache = json.load(open(CONFIG, encoding="utf-8")) if os.path.exists(CONFIG) else {}
    return _cache


def cfg(key, default=None):
    v = config().get(key, default)
    if v is None:
        raise SystemExit("config key %r is not set (see config/customslop.example.json)" % key)
    return v


def opt(key, default=None):
    return config().get(key, default)


def workdir():
    return opt("workdir") or ROOT


def data(name):
    """Files extracted by tools/setup_data.py (items_game.txt, mvm_upgrades.txt, *_strings.txt)."""
    return os.path.join(workdir(), "data", name)


def data_dir():
    return os.path.join(workdir(), "data")


def server_root():
    return cfg("server_root")


def af_schema():
    """The custom schema the live server currently serves (April Fools + tf2cc etc.)."""
    return os.path.join(server_root(), "scripts", "items", "custom_items_game.txt")


def loc_files():
    out = []
    c = opt("tf2_client_dir")
    if c:
        out.append(os.path.join(c, "tf", "resource", "tf_english.txt"))
    s = opt("tf2_server_dir")
    if s:
        out.append(os.path.join(s, "tf", "resource", "tf_english.txt"))
    out += [os.path.join(server_root(), "resource", "tf_english.txt"),
            os.path.join(server_root(), "resource", "tf2classified_english.txt")]
    t = opt("tf2c_client_dir")
    if t:
        out.append(os.path.join(t, "tf2classified", "resource", "tf2classified_english.txt"))
    return out
