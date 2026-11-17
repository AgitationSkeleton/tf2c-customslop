"""CustomSlop catalogue + review queue CLI (named slopqueue.py, not queue.py: a tools/queue.py would shadow
Python's stdlib queue module, which requests/urllib3 import).

Modes (config "mode"):
  review      (now)   generated weapons wait in queue/pending/ for a human approve/reject
  automation  (after the user's go-ahead) the nightly job generates `daily_count` weapons and
                      marks them approved itself; the queue stays as an optional manual override
                      (reject/pull a weapon early, regenerate tonight's batch)

The catalogue (state/catalogue.json) is CustomSlop's persistent memory and the ONLY thing any
prune/rotate/delete step may act on (HARD_RULES.txt): every defindex it reserved, every asset
path it produced, status (pending/approved/live/retired/rejected), dates, announcements.
Defindexes are monotonic and never reused (a rejected or retired id is burned).

  python -I tools/slopqueue.py generate [--count N] [--test-batch]
  python -I tools/slopqueue.py list | show <id> | approve <id> | reject <id> | pull <id>
  python -I tools/slopqueue.py export-approved          -> bundle/<stamp>/ (schema fragment + asset list), no deploy
  python -I tools/slopqueue.py index                    -> queue/index.json for the review gallery
"""
import argparse
import datetime as dt
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

STATE_DIR = os.environ.get("CUSTOMSLOP_STATE_DIR") or os.path.join(ROOT, "state")
CFG = os.path.join(STATE_DIR, "customslop.json") if os.path.exists(os.path.join(STATE_DIR, "customslop.json"))     else os.path.join(ROOT, "config", "customslop.json")
STATE = os.path.join(STATE_DIR, "catalogue.json")
QUEUE = os.environ.get("CUSTOMSLOP_QUEUE_DIR") or os.path.join(ROOT, "queue")   # override: dry runs only
DEFAULT_CFG = {
    "mode": "review",                 # review | automation   (automation only after the user's go-ahead)
    "daily_count": 3,
    "cap": 50,                        # CustomSlop weapons only; stock / April Fools / tf2cc never count
    "defindex_first": 26000, "defindex_last": 29999,
    "ill_fit": 0.15, "multi": 0.10,
    "asset_tier": 2,                  # 1 = stats only (donor models/icons), 2 = mutated + recoloured + rendered
    "publish_target": "fastdl_repo",  # user decision: agitationskeleton/redchanitfastdl_tf2classic (prefix tf2classified/)
    "apply_hook": "UNDECIDED",        # "runservers_bat" (one line before the .lnk loop) | "scheduled_task"
    "fonts_dir": None,                # folder with tf2build.ttf + tf2secondary.ttf; None = find the TF2 install
    "discord_enabled": False,         # posts only after a successful nightly apply (automation mode)
    "server_root": None,              # from config/customslop.json
    "vpk_exe": None,                  # Valve's vpk.exe (e.g. <TF2 dedicated server>/bin/vpk.exe): builds the schema VPK
    "gate_port": 27993,               # schemagate.py: isolated LAN srcds on 127.0.0.1
    "gate_timeout": 60,               # per gate boot (a boot takes ~15 s)
}


def cfg():
    c = dict(DEFAULT_CFG)
    if os.path.exists(CFG):
        c.update(json.load(open(CFG)))
    return c


def load_state(c):
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"next_defindex": c["defindex_first"], "weapons": {}, "burned": [], "journal": [], "announcements": []}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, STATE)                      # atomic on NTFS


def journal(st, what, **kw):
    st["journal"].append(dict(t=dt.datetime.now().isoformat(timespec="seconds"), what=what, **kw))


def reserve(st, c):
    di = st["next_defindex"]
    if di > c["defindex_last"]:
        raise SystemExit("CustomSlop defindex range exhausted")
    st["next_defindex"] = di + 1
    return di


def own(st, di):
    """Hard-rule guard: refuse anything not in CustomSlop's own catalogue and range."""
    c = cfg()
    w = st["weapons"].get(str(di))
    if w is None or not (c["defindex_first"] <= int(di) <= c["defindex_last"]):
        raise SystemExit("refused: %s is not a CustomSlop catalogue item" % di)
    return w


TEST_RECIPES = [
    dict(label="ill-fitting class", ill_fit=True, families=["hitscan"], need_world=True),
    dict(label="multi-class", multi=True, multi_n=2, families=["melee"]),
    dict(label="projectile-model override", proj_model=True, families=["rocket", "grenade"], need_world=True),
    dict(label="MvM upgrade attributes", mvm=3, families=["hitscan", "projectile"]),
    dict(label="silly-but-safe extreme", extreme=True, n_attr=8, force=["customslop_ignite_self", "set_dmgtype_ignite"]),
    dict(label="flame", families=["flame"]),
    dict(label="explosive", families=["grenade", "rocket"]),
    dict(label="melee", families=["melee"]),
    dict(label="nail/projectile", families=["projectile"]),
    dict(label="random"),
]


FIRST_RECIPES = [   # first deployment: three ordinary (not test-extreme) weapons, different classes and slots
    dict(label="first-deploy primary", families=["hitscan", "rocket", "flame", "projectile"], need_world=True, slot="primary"),
    dict(label="first-deploy secondary", families=["hitscan", "grenade", "projectile"], need_world=True, slot="secondary"),
    dict(label="first-deploy melee", families=["melee"], need_world=True, slot="melee"),
]


def cmd_generate(a):
    import pipeline
    c = cfg()
    st = load_state(c)
    c["_attr_registry"] = st.setdefault("attr_defs", {})
    c["_used_hues"] = st.setdefault("used_hues", [])
    ctx = pipeline.Ctx(c)
    import names
    used = names.History.from_catalogue(st["weapons"], ROOT)   # names + descriptions ever made: never repeat/similar
    keep, gone = [], None
    if a.first_deploy and a.replace:
        old = json.load(open(os.path.join(QUEUE, "first_deploy.json")))["weapons"]
        keep = [w for w in old if w["id"] != a.replace]
        gone = next((w for w in old if w["id"] == a.replace), None)
        if gone is not None:
            cmd_reject(argparse.Namespace(id=str(a.replace)))
        else:   # already gone (earlier failed replace): regenerate whichever slot is missing
            have = {w["slot"] for w in keep}
            gone = {"slot": next(r["slot"] for r in FIRST_RECIPES if r["slot"] not in have)}
        st = load_state(c)
        c["_attr_registry"] = st.setdefault("attr_defs", {})
        c["_used_hues"] = st.setdefault("used_hues", [])
        ctx.attr_registry = c["_attr_registry"]
    recipes = [r for r in FIRST_RECIPES if r["slot"] == gone["slot"]] if gone else \
        TEST_RECIPES if a.test_batch else FIRST_RECIPES if a.first_deploy else \
        [dict(label="nightly")] * (a.count or c["daily_count"])
    seed = a.seed if a.seed is not None else int(dt.datetime.now().strftime("%Y%m%d%H"))
    rng = random.Random(seed)
    taken_classes = {c_ for w in keep for c_ in w["classes"]}
    made = []
    for r in recipes:
        for attempt in range(10):
            di = reserve(st, c)
            save_state(st)                                   # reservation persists before any work
            out = os.path.join(QUEUE, "pending", str(di))
            try:
                s = pipeline.make_weapon(ctx, di, rng, out, dict(r, avoid_classes=sorted(taken_classes)), used)
                g = s["gate"] or {}
                if not (g.get("structural") and g.get("render_gate")) or g.get("fallback"):
                    raise RuntimeError("gate not passed cleanly: %s" % g)
                if a.first_deploy and set(s["classes"]) & taken_classes:
                    raise RuntimeError("class already used by another first-deploy candidate")
            except Exception as e:                           # failed weapon: burn the id, record, retry
                st["burned"].append(di)
                journal(st, "generate_failed", defindex=di, error=repr(e)[:300])
                save_state(st)
                shutil.rmtree(out, ignore_errors=True)
                print("REROLL", di, repr(e)[:160])
                s = None
                continue
            break
        if s is None:
            continue
        taken_classes |= set(s["classes"])
        made.append(di)
        st["attr_defs"] = ctx.attr_registry
        st["used_hues"] += [[dt.date.today().isoformat(), h] for h in s["colours"]["hues"]]
        status = "approved" if c["mode"] == "automation" else "pending"
        st["weapons"][str(di)] = dict(defindex=di, name=s["name"], classes=s["classes"], slot=s["slot"],
                                      base=s["base"], status=status, created=dt.date.today().isoformat(),
                                      recipe=r.get("label"), dir=os.path.relpath(out, ROOT),
                                      assets=[m["path"] for m in s["assets"]], asset_bz2=s["asset_bz2"],
                                      credit=s["base"]["credit"], gate={k: s["gate"].get(k) for k in (
                                          "attempt", "structural", "engine_ok", "hands_ok", "arms_ok", "render_gate",
                                          "detail", "size")})
        journal(st, "generated", defindex=di, name=s["name"], status=status)
        save_state(st)
        print(di, s["name"], s["classes"], s["slot"], s["base"]["item_class"], "|", r.get("label"), "|", s["gate"])
    write_index(st)
    if a.first_deploy:
        rows = list(keep)
        for di in made:
            w = st["weapons"][str(di)]
            d = os.path.join(ROOT, w["dir"])
            sm = json.load(open(os.path.join(d, "summary.json")))
            rows.append(dict(id=di, name=w["name"], classes=list(w["classes"]), slot=w["slot"],
                             base=w["base"]["item_class"], card_png=os.path.join(d, "card.png"),
                             icon_png=os.path.join(d, "icon.png"), render_png=os.path.join(d, "render.png"),
                             asset_bytes=sm["asset_bytes"], card_lines=sm["card_lines"]))
        json.dump(dict(generated=dt.datetime.now().isoformat(timespec="seconds"), status="pending (not approved, not published)",
                       weapons=rows), open(os.path.join(QUEUE, "first_deploy.json"), "w"), indent=1)


def write_index(st):
    rows = []
    for w in sorted(st["weapons"].values(), key=lambda x: x["defindex"]):
        d = os.path.join(ROOT, w["dir"])
        s = json.load(open(os.path.join(d, "summary.json"))) if os.path.exists(os.path.join(d, "summary.json")) else {}
        rows.append(dict(id=w["defindex"], name=w["name"], status=w["status"], classes=list(w["classes"]),
                         class_slots=w["classes"], slot=w["slot"], base=w["base"]["item_class"],
                         base_item=w["base"], recipe=w.get("recipe"), description=s.get("description"),
                         card_lines=s.get("card_lines"), card_png=os.path.join(d, "card.png"),
                         icon_png=os.path.join(d, "icon.png"), render_png=os.path.join(d, "render.png"),
                         render_orig_png=os.path.join(d, "render_orig.png"), summary_json=os.path.join(d, "summary.json"),
                         item_fragment=os.path.join(d, "item.txt"), gate=w.get("gate"),
                         asset_bytes=s.get("asset_bytes")))
    os.makedirs(QUEUE, exist_ok=True)
    json.dump(dict(generated=dt.datetime.now().isoformat(timespec="seconds"), weapons=rows),
              open(os.path.join(QUEUE, "index.json"), "w"), indent=1)


def cmd_list(a):
    st = load_state(cfg())
    for w in sorted(st["weapons"].values(), key=lambda x: x["defindex"]):
        print(w["defindex"], w["status"].ljust(9), w["name"].ljust(42), "/".join(w["classes"]), w["slot"], w["base"]["item_class"])


def cmd_show(a):
    st = load_state(cfg())
    w = own(st, a.id)
    print(open(os.path.join(ROOT, w["dir"], "summary.json")).read())


def move(st, w, sub):
    src = os.path.join(ROOT, w["dir"])
    dst = os.path.join(QUEUE, sub, str(w["defindex"]))
    if os.path.abspath(src) != os.path.abspath(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        w["dir"] = os.path.relpath(dst, ROOT)


def cmd_approve(a):
    st = load_state(cfg())
    w = own(st, a.id)
    w["status"] = "approved"
    move(st, w, "approved")
    journal(st, "approved", defindex=w["defindex"])
    save_state(st)
    write_index(st)


def cmd_reject(a):
    st = load_state(cfg())
    w = own(st, a.id)
    if w["status"] in ("live",):
        raise SystemExit("live weapon: use 'pull' (removed at the next apply), not reject")
    shutil.rmtree(os.path.join(ROOT, w["dir"]), ignore_errors=True)
    del st["weapons"][str(w["defindex"])]
    st["burned"].append(w["defindex"])                    # never reused
    journal(st, "rejected", defindex=w["defindex"], name=w["name"])
    save_state(st)
    write_index(st)


def cmd_pull(a):
    st = load_state(cfg())
    w = own(st, a.id)
    w["status"] = "pull"                                  # the next apply removes it (own items only)
    journal(st, "pull_requested", defindex=w["defindex"])
    save_state(st)


def attribute_block(st):
    """CustomSlop's own attribute definitions (25900 VScript effect + display fixes), KeyValues."""
    rows = [dict(id=25900, name="customslop ignite self on attack", cls="customslop_ignite_self",
                 fmt="value_is_additive", effect="negative",
                 desc_text="Sets the wielder on fire for %s1 seconds on every attack")]
    rows += [dict(d, name=n) for n, d in st.get("attr_defs", {}).items()]
    out = []
    for r in sorted(rows, key=lambda r: r["id"]):
        desc = r.get("desc") or r.get("desc_text")
        b = ['"%d"' % r["id"], "{", '	"name"	"%s"' % r["name"], '	"attribute_class"	"%s"' % r["cls"],
             '	"description_string"	"%s"' % desc, '	"description_format"	"%s"' % r["fmt"],
             '	"effect_type"	"%s"' % r["effect"], '	"hidden"	"0"', '	"stored_as_integer"	"0"', "}"]
        out.append(NL.join(b))
    return NL.join(out) + NL


NL = chr(10)


def cmd_export(a):
    st = load_state(cfg())
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(ROOT, "bundle", stamp)
    os.makedirs(out)
    frag, assets = [], []
    for w in sorted(st["weapons"].values(), key=lambda x: x["defindex"]):
        if w["status"] not in ("approved", "live"):
            continue
        d = os.path.join(ROOT, w["dir"])
        frag.append(open(os.path.join(d, "item.txt"), encoding="utf-8").read())
        assets += [dict(defindex=w["defindex"], path=p, src=os.path.join(d, "files", p)) for p in w["assets"]]
    open(os.path.join(out, "customslop_items_fragment.txt"), "w", encoding="utf-8").write("\n".join(frag))
    open(os.path.join(out, "customslop_attributes_fragment.txt"), "w", encoding="utf-8").write(attribute_block(st))
    json.dump(assets, open(os.path.join(out, "assets.json"), "w"), indent=1)
    json.dump(dict(stamp=stamp, weapons=[w["defindex"] for w in st["weapons"].values() if w["status"] in ("approved", "live")],
                   note="export only - nothing deployed"), open(os.path.join(out, "bundle.json"), "w"), indent=1)
    print(out, len(frag), "items", len(assets), "assets")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("generate")
    g.add_argument("--count", type=int)
    g.add_argument("--seed", type=int)
    g.add_argument("--test-batch", action="store_true")
    g.add_argument("--first-deploy", action="store_true")
    g.add_argument("--replace", type=int, help="with --first-deploy: reject this candidate and regenerate only its slot")
    sp.add_parser("list")
    sp.add_parser("index")
    sp.add_parser("export-approved")
    for n in ("show", "approve", "reject", "pull"):
        x = sp.add_parser(n)
        x.add_argument("id")
    a = ap.parse_args()
    {"generate": cmd_generate, "list": cmd_list, "show": cmd_show, "approve": cmd_approve, "reject": cmd_reject,
     "pull": cmd_pull, "export-approved": cmd_export, "index": lambda a: write_index(load_state(cfg()))}[a.cmd](a)


if __name__ == "__main__":
    main()
