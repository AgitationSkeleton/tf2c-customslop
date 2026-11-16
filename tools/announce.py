"""CustomSlop Discord announcement: TF2-style item cards as attachments.

Two kinds of post:
  --preview          ONE labelled preview of the review queue's test batch (allowed once by the user)
  (default)          the nightly post for the weapons a successful apply actually put live
                     (catalogue "announcements" entries with posted=false; automation mode only)
The webhook URL is read only at post time from %USERPROFILE%\\.customslop\\secrets.json, key
"discord_webhook_url"; it is never printed, logged, stored elsewhere or passed on argv.
Discord limits: <= 10 attachments per message, content <= 2000 chars; more cards go into
follow-up messages; 429 -> wait retry_after (+ jitter) and retry, up to 5 tries; 5xx -> backoff.
Every attempt is journaled in the catalogue (status code, message id; never the URL).

  python -I announce.py --preview [--dry-run]
  python -I announce.py [--dry-run]
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.append(HERE)                   # appended: keep stdlib modules first on the path
import slopqueue as Q  # noqa: E402

SECRET = os.path.join(os.path.expanduser("~"), ".customslop", "secrets.json")


def webhook():
    with open(SECRET, encoding="utf-8") as f:
        return json.load(f)["discord_webhook_url"]


def post(url, payload, files):
    import requests
    last = None
    for attempt in range(5):
        mp = [("payload_json", (None, json.dumps(payload), "application/json"))]
        handles = []
        for i, (name, path) in enumerate(files):
            fh = open(path, "rb")
            handles.append(fh)
            mp.append(("files[%d]" % i, (name, fh, "image/png")))
        try:
            r = requests.post(url + "?wait=true", files=mp, timeout=60)
        except Exception as e:                 # network error: back off, never leak the URL
            last = type(e).__name__
            time.sleep(2 ** attempt + random.random())
            continue
        finally:
            for fh in handles:
                fh.close()
        last = r.status_code
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + random.random())
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt + random.random())
            continue
        if r.ok:
            return True, r.status_code, r.json().get("id")
        return False, r.status_code, None
    return False, last, None


def messages(weapons, title):
    """Split into Discord-sized messages: up to 10 cards each."""
    out = []
    for k in range(0, len(weapons), 10):
        chunk = weapons[k:k + 10]
        files = [("card_%d.png" % w["id"], w["card_png"]) for w in chunk]
        lines = ["**%s** (%s, %s)" % (w["name"], "/".join(w["classes"]), w["slot"]) for w in chunk]
        content = (title + ("" if k == 0 else " (continued)") + "\n" + "\n".join(lines))[:2000]
        out.append((dict(username="CustomSlop", content=content, allowed_mentions={"parse": []}), files))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", help="comma-separated defindexes to include in a preview")
    ap.add_argument("--first-deploy", action="store_true", help="preview only the weapons in queue/first_deploy.json")
    a = ap.parse_args()
    c = Q.cfg()
    st = Q.load_state(c)
    idx = json.load(open(os.path.join(Q.QUEUE, "index.json")))
    if a.preview:
        ws = [w for w in idx["weapons"] if w["status"] in ("pending", "approved")]
        if a.first_deploy:
            a.ids = ",".join(str(w["id"]) for w in json.load(open(os.path.join(Q.QUEUE, "first_deploy.json")))["weapons"])
        if a.ids:
            want = {int(x) for x in a.ids.split(",") if x.strip()}
            ws = [w for w in idx["weapons"] if w["id"] in want]
        title = ("**PREVIEW / TEST - not live yet.** CustomSlop will add 3 random new weapons to TF2C #2 "
                 "every day (up to 50 at a time). Preview of %d weapon%s:" % (len(ws), "" if len(ws) == 1 else "s"))
        targets = [None]
    else:
        if c["mode"] != "automation" or not c.get("discord_enabled"):
            sys.exit("nightly posts only in automation mode with discord_enabled")
        targets = [x for x in st.get("announcements", []) if not x.get("posted")]
        ws = None
    for tgt in targets:
        if tgt is not None:
            ids = set(tgt["weapons"])
            ws = [w for w in idx["weapons"] if w["id"] in ids]
            title = "Today's %d new CustomSlop weapons are live on TF2C #2:" % len(ws)
            if not ws:
                tgt["posted"] = True
                continue
        msgs = messages(ws, title)
        if a.dry_run:
            print(json.dumps([dict(content=m[0]["content"], files=[f[0] for f in m[1]]) for m in msgs], indent=1))
            continue
        url = webhook()
        ok_all = True
        for payload, files in msgs:
            ok, code, mid = post(url, payload, files)
            Q.journal(st, "discord_post", ok=ok, status=code, message_id=mid, files=len(files),
                      kind="preview" if tgt is None else "nightly")
            ok_all &= ok
            time.sleep(1.5)
        if tgt is None and ok_all:
            Q.journal(st, "discord_preview_posted", ids=[w["id"] for w in ws])
        if tgt is not None:
            tgt["posted"] = ok_all
        Q.save_state(st)
        print("posted" if ok_all else "post failed (see journal)")


if __name__ == "__main__":
    main()
