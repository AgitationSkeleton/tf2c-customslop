# tf2c-customslop

**CustomSlop** adds a few new, randomly generated custom weapons to a TF2 Classified
(build 5205) server every day: random stats from the whole item schema, random names and
descriptions, mutated and recoloured models, rendered icons, random sounds and TF2-style item
cards for Discord. The live set is capped (default 50) and the oldest CustomSlop weapons rotate
out. Stock items, other custom packs (e.g. April Fools, tf2cc) and every file CustomSlop did not
create itself are never touched.

This repository is the method and the code. It contains **no game assets, no fonts, no
credentials**; it reads your own installs at run time (see CREDITS.md).

## Pipeline (one weapon)

1. **Roll**: a donor weapon (TF2C stock, April Fools, optional Open Fortress / MarxVee / presplit /
   TF2 Classic beta donors), its class(es) and slot (sometimes an ill-fitting or extra class), and
   3-8 attributes drawn from **every** attribute in the schema, MvM upgrades included
   (`tools/attrpool.py`: allowed / guarded / excluded, each exclusion with its reason; useless-on-
   this-base attributes stay allowed but weighted low).
2. **Mutate** (`tools/mutate.py`): binary edits of the compiled model, no decompile. Droop, twist,
   bend, blunderbuss flare, distended barrels, squash, wobble, stretch and per-part rescaling.
   Long low-poly parts deform piecewise-affinely (no faceting). The grip region and everything
   skinned to hand/finger/arm bones is frozen (hand positions from the decoded idle animation), so
   the class arms still hold the weapon. Normals, tangents, attachments (muzzle follows the barrel)
   and bounding boxes are updated; VTX and bones are untouched.
3. **Recolour** (`tools/regions.py`, `tools/palette.py`): the model is split into grip / body /
   front / accent regions, mapped to UV masks, and each region gets a colour from a broad palette
   (hue wheel, pastel, neon, metals, woods, neutrals, team colours, greyscale, gradients) with
   hue-repeat avoidance. Textures are capped at 256 px (DXT1 unless alpha is used).
4. **Sounds** (`tools/sounds.py`): random fire/reload/empty/deploy/melee sounds from content every
   client already has (TF2C, TF2, HL2): ~70% weapon sounds, ~23% other effects, ~7% voice lines.
   Loops, overlong and earrape-prone files are rejected.
5. **Icon** (`tools/iconfit.py`): a software renderer whose camera and lighting are fitted to the
   donor's own stock icon, so the result looks like a stock icon.
6. **Card** (`tools/card.py`, `tools/attrdesc.py`): TF2's item-info card, with TF2's own attribute
   description strings and formats (`value_is_percentage`, `inverted_percentage`, `additive`, ...),
   coloured by `effect_type`.
7. **Gates** (all automatic; a failing weapon is re-rolled, never shipped): see below.

## Safety gates

* **Schema gate.** Build 5205 rejects the **whole** custom schema ("Item schema load failed") if one
  item uses an attribute with no definition, a value it cannot parse, or a **set-bonus attribute**
  (found with the engine-load test). Every item is checked at generation and again at apply.
* **Engine checks** (`tools/validate_model.py`): MDL/VVD/VTX headers and checksums, VTX strip and
  bone limits, finite data, weights summing to 1, bounding boxes, a size cap on the extent,
  VTF/VMT validity.
* **Hand-rig checks**: grip vertices and hand attachments unchanged, bones identical, the class arms
  bonemerge (per side) onto the view model.
* **Render gate**: silhouette area, no new dark regions, no fragmentation or spikes.
* **Size cap**: <= 1 MB bz2 per weapon (models + textures + icon).
* **Engine-load test** (`tools/enginetest.py`): an isolated, LAN-only, bots-only dedicated server
  (a copy of the binaries in your own folder; no game client, no Steam login) precaches and spawns
  every model and gives each item to a bot over local RCON.

## Hard rules (what CustomSlop may change)

* It only adds, rotates or deletes **items and files it created and recorded in its own catalogue**
  (`state/catalogue.json`, its own defindex range, the exact asset paths it published).
* It never removes or modifies other custom items (April Fools, tf2cc, ...), stock items, or any
  FastDL file it did not create. Defindexes are never reused.
* The served schema (`scripts/items/custom_items_game.txt`) is shared: with `allow_schema_replace`
  the merge keeps every other byte identical and *proves* it each time (`tools/apply.py merge`).
* It never restarts the server, never uses RCON on the live server, never touches the hostname.

## Daily cycle (automation mode)

| Time | Step |
|---|---|
| 02:00 | `nightly.py prepare` (scheduled task running python.exe directly): generate `daily_count` weapons, publish their files + the merged schema to FastDL in **one commit** via the GitHub Git Data API, wait for the Pages build (re-trigger once if stuck), check every URL returns 200 |
| server restart window | `nightly.py apply`, called from your restart script while the servers are **down** (one line before the servers are relaunched): lock + journal + rollback, own items only, rotation beyond `cap`, bounded time so it can never block the launch; then the Discord post (detached) |

Review mode (`"mode": "review"`) generates into `queue/pending/` for a human instead
(`tools/slopqueue.py list | show | approve | reject | pull | export-approved`).

## Setup

1. Python 3.12+ with `numpy`, `Pillow`, `requests`; the GitHub CLI (`gh`, logged in) for publishing.
2. Copy `config/customslop.example.json` to `config/customslop.json` and fill in your paths.
3. `python -I tools/setup_data.py` (extracts the schema/strings indexes from your installs),
   `python -I tools/donor_audit.py`, optionally `python -I tools/fit_icons.py --all`.
4. Try it: `python -I tools/slopqueue.py generate --count 3`, look at `queue/pending/*/card.png`.
5. Secrets: copy `secrets.example.json` to `%USERPROFILE%\.customslop\secrets.json` (outside the
   repo) and put your Discord webhook URL there. Nothing else holds credentials.
6. Server: build `plugin/customslop.sp` with SourceMod's compiler
   (`spcomp64 -i <sourcemod>/scripting/include -o customslop.smx plugin/customslop.sp`) and put the
   .smx in `addons/sourcemod/plugins/`. It shows the chat ad and adds the live CustomSlop files to
   the download table. Optional VScript effects: `vscripts/customslop/sv_customslop.nut`.
7. Restart hook: in the script that relaunches your servers, add one line before the launch:
   `"<python.exe>" -I "<repo>\tools\nightly.py" apply >> "<repo>\state\nightly.log" 2>&1`
8. Scheduled task for 02:00: run `<python.exe> -I "<repo>\tools\nightly.py" prepare` directly
   (not through cmd, so "kill all cmd.exe" maintenance tasks cannot stop it).
9. Switch `"mode"` to `"automation"` when you are happy with the review results.

Rollback: `tools/publish.py --revert <sha> --apply` (FastDL), remove `custom/00customslop*` and
restore the loose schema on the server, remove the hook and the task.

## Licence

GPL-3.0. See CREDITS.md for the donor content authors.
