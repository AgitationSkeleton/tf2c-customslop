"""Tests for the nightly apply step against a SANDBOX copy of the TF2C server's schema files.

Proves (HARD_RULES.txt): every non-CustomSlop item/attribute/file survives apply + rotation
unchanged; a failure or a hard crash mid-apply leaves (or restores) the previous working schema;
re-running is idempotent; rotation touches only CustomSlop's own catalogued assets.
Uses its own catalogue copy (state_test/), never the review queue's state.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cspaths as P  # noqa: E402
LIVE = P.server_root()
SB = os.path.join(ROOT, "sandbox_server", "tf2classified")
TST = os.path.join(ROOT, "state_test")
COPY = ["custom/00tf2cc_schema.vpk", "custom/aprilfools2026.vpk", "scripts/items/custom_items_game.txt"]
DECOYS = {"custom/00customslop/models/not_customslop/decoy.mdl": b"decoy - not CustomSlop's",
          "custom/0tf2cc_merc/models/tf2cc/decoy.txt": b"tf2cc decoy"}


def h(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None


def snapshot():
    out = {}
    for dp, _, fs in os.walk(SB):
        for f in fs:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, SB).replace("\\", "/")] = h(p)
    return out


def run(env=None, extra=()):
    e = dict(os.environ, CUSTOMSLOP_STATE_DIR=TST, **(env or {}))
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, "apply_test_entry.py"), SB, *extra],
                          capture_output=True, text=True, env=e)


def main():
    import apply as A
    import slopqueue as Q
    import vfs
    import kv
    shutil.rmtree(os.path.join(ROOT, "sandbox_server"), ignore_errors=True)
    for rel in COPY:
        os.makedirs(os.path.dirname(os.path.join(SB, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(LIVE, rel), os.path.join(SB, rel))      # read-only copy of live files
    for rel, b in DECOYS.items():
        os.makedirs(os.path.dirname(os.path.join(SB, rel)), exist_ok=True)
        open(os.path.join(SB, rel), "wb").write(b)
    # test catalogue: a copy of the review catalogue with every pending weapon approved
    shutil.rmtree(TST, ignore_errors=True)
    os.makedirs(TST)
    st = json.load(open(Q.STATE))
    # test set: the first-deployment candidates (the older test batch predates the 5205 schema gate and
    # contains set-bonus attributes, which apply now correctly refuses)
    fd = {w["id"] for w in json.load(open(os.path.join(Q.QUEUE, "first_deploy.json")))["weapons"]}
    st["weapons"] = {k: w for k, w in st["weapons"].items() if w["defindex"] in fd}
    for w in st["weapons"].values():
        w["status"], w["published"] = "approved", True   # test: pretend FastDL verified
    json.dump(st, open(os.path.join(TST, "catalogue.json"), "w"), indent=1)
    res = {}
    before = snapshot()
    base_schema = vfs.VPK(os.path.join(SB, "custom/00tf2cc_schema.vpk")).read("scripts/items/custom_items_game.txt")

    # 1. injected failure after 2 steps -> rolled back, sandbox unchanged
    r = run(extra=["--fail-after", "2"])
    res["1_injected_failure_rolled_back"] = snapshot() == before and "rolled back" in r.stdout
    # 2. hard crash after 3 steps -> journal left behind; next run rolls back then applies
    r = run(env={"CUSTOMSLOP_TEST_CRASH_AFTER": "3"})
    res["2a_crash_left_journal"] = os.path.exists(os.path.join(TST, "apply_txn.json")) and r.returncode == 3
    r = run()
    res["2b_recovered_and_applied"] = "rolled back" in r.stdout and "applied txn" in r.stdout
    after = snapshot()
    merged = open(os.path.join(SB, A.LOOSE), "rb").read()
    vpk_m = vfs.VPK(os.path.join(SB, A.SCHEMA_VPK)).read("scripts/items/custom_items_game.txt")
    res["3_loose_equals_vpk"] = merged == vpk_m
    # 4. every non-CustomSlop item and attribute identical (structural) and base text preserved
    c = Q.cfg()
    b_ig = kv.parse(base_schema.decode("utf-8", "replace"))[0].get("items_game")
    m_ig = kv.parse(merged.decode("utf-8", "replace"))[0].get("items_game")
    same = True
    for sec in ("items", "attributes"):
        A_ = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in b_ig.get(sec).pairs if not A.is_own(k, c)}
        B_ = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in m_ig.get(sec).pairs if not A.is_own(k, c)}
        same &= A_ == B_
    res["4_non_customslop_items_identical"] = same
    txt = merged.decode("utf-8")
    import re
    stripped = re.sub(r"\n// ---- CustomSlop \(generated; do not edit\) ----\n.*?// ---- end CustomSlop ----\n", "", txt, flags=re.S)
    res["4b_base_text_byte_identical_outside_customslop_blocks"] = stripped.encode("utf-8") == base_schema
    own_n = sum(1 for k, _ in m_ig.get("items").pairs if A.is_own(k, c))
    res["5_customslop_items_in_schema"] = own_n
    untouched = [p for p in before if before[p] != after.get(p) and p not in (A.LOOSE,)]
    res["6_only_expected_files_changed"] = untouched == []
    res["6b_decoys_and_tf2cc_af_vpks_untouched"] = all(after[p] == before[p] for p in
                                                       list(DECOYS) + ["custom/00tf2cc_schema.vpk", "custom/aprilfools2026.vpk"])
    # 7. idempotent re-run: same schema bytes
    r = run()
    res["7_rerun_idempotent"] = open(os.path.join(SB, A.LOOSE), "rb").read() == merged
    # 8. rotation at a tiny cap: only own catalogued assets removed; decoys/base untouched
    cfgp = os.path.join(TST, "customslop.json")
    cc = dict(Q.DEFAULT_CFG, cap=1)
    json.dump(cc, open(cfgp, "w"))
    pre = snapshot()
    r = run()
    post = snapshot()
    stt = json.load(open(os.path.join(TST, "catalogue.json")))
    retired = [w for w in stt["weapons"].values() if w["status"] == "retired"]
    removed = sorted(set(pre) - set(post))
    own_paths = {"custom/00customslop/" + p for w in retired for p in w["assets"]}
    res["8_rotation_retired"] = len(retired)
    res["8b_removed_only_own_catalogued_assets"] = bool(removed) and set(removed) <= own_paths
    res["8c_decoys_tf2cc_af_survive"] = all(post.get(p) == pre.get(p) for p in
                                            list(DECOYS) + ["custom/00tf2cc_schema.vpk", "custom/aprilfools2026.vpk"])
    m2 = kv.parse(open(os.path.join(SB, A.LOOSE), encoding="utf-8").read())[0].get("items_game")
    res["8d_schema_now_has_cap_items"] = sum(1 for k, _ in m2.get("items").pairs if A.is_own(k, c))
    same = True
    for sec in ("items", "attributes"):
        A_ = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in b_ig.get(sec).pairs if not A.is_own(k, c)}
        B_ = {k: kv.dump(v) if isinstance(v, kv.KV) else v for k, v in m2.get(sec).pairs if not A.is_own(k, c)}
        same &= A_ == B_
    res["8e_non_customslop_items_identical_after_rotation"] = same
    res["journal_tail"] = [j["what"] for j in stt["journal"][-6:]]
    json.dump(res, open(os.path.join(ROOT, "tests_apply_result.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
