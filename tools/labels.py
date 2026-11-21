"""Item labels and donor-key hygiene for CustomSlop items (TF2 Classified build 5205).

Two user-visible bugs this prevents (found live 2026-11-16):
  * item_type_name copied from a tf2cc Merc donor ("Mercenary Weapon"), or a token TF2C does not
    localise ("#TF_Weapon" exists only in TF2's tf_english.txt, so TF2C shows the raw token).
    The type token must resolve in TF2C's OWN localisation files (resource/tf_english.txt +
    tf2classified_english.txt of the TF2C install), never TF2's.
  * Merc / tf2cc-only keys copied onto a non-Merc item: static attr "custom hand viewmodel"
    (c_merc_arms.mdl), Merc's ACT_DOD_* animation_replacement, tf2cc sound scripts / particles /
    projectile models, tf2cc tags.

  type_token(...)   pick a TF2C-localised item_type_name for an item class
  sanitize(...)     copy of a donor KV with every Merc/tf2cc-only key removed (non-Merc items)
  label_check(...)  gate: errors for any item in a schema fragment that breaks these rules
"""
import os
import re

import kv

import loc

TF2CC_SRCS = {"of_merc", "marxvee"}                     # donors that are tf2cc's Merc/MarxVee items
MERC_STATIC = {"custom hand viewmodel"}
STOCK_SRCS = {"tf2c", "aprilfools"}                     # donors whose own type token may be kept
_MERC_WORD = re.compile(r"\bmercenary\b", re.I)
_TF2CC_REF = re.compile(r"tf2cc|c_merc_arms|/merc/|^ACT_DOD_", re.I)


def tf2c_tokens(server_root):
    """Lower-case token -> text from the TF2C install's own resource files only."""
    files = [os.path.join(server_root, "resource", f) for f in ("tf_english.txt", "tf2classified_english.txt")]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise RuntimeError("TF2C localisation file(s) missing: %s" % missing)
    return loc.Loc(files).tokens


def _eff(it, key, prefabs, depth=0):
    v = it.get(key)
    if v is not None or depth > 6:
        return v
    for p in (it.get("prefab") or "").split():
        b = prefabs.get(p.lower())
        if b is not None:
            v = _eff(b, key, prefabs, depth + 1)
            if v is not None:
                return v
    return None


def stock_types(stock_schema, tokens):
    """{(item_class, slot): token, item_class: token} from the stock 5205 items_game (prefabs
    resolved), keeping only tokens TF2C localises; lowest defindex wins."""
    pf = {k.lower(): b for k, b in stock_schema.get("prefabs").blocks()} if stock_schema.get("prefabs") else {}
    out = {}
    for k, it in sorted(((k, it) for k, it in stock_schema.get("items").blocks() if k.isdigit()), key=lambda x: int(x[0])):
        ic, t, sl = _eff(it, "item_class", pf), _eff(it, "item_type_name", pf), _eff(it, "item_slot", pf)
        if ic and t and t.startswith("#") and t[1:].lower() in tokens:
            out.setdefault((ic, sl), t)
            out.setdefault(ic, t)
    return out


def type_token(item_class, slot, src, donor_itn, tokens, stock):
    """A TF2C-localised '#token' for this item class, or None (caller then uses a literal name)."""
    def ok(t):
        return bool(t) and t.startswith("#") and t[1:].lower() in tokens
    if src in STOCK_SRCS and ok(donor_itn) and not _MERC_WORD.search(tokens[donor_itn[1:].lower()]):
        return donor_itn
    for key in ((item_class, slot), item_class):
        if ok(stock.get(key)):
            return stock[key]
    stem = re.sub(r"^tf2?c?_weapon_", "", item_class or "")
    for cand in ("#TF_Weapon_" + stem, "#TF_Weapon_" + stem.split("_")[0]):
        if ok(cand):
            return cand
    return None


def donor_type_name(src, dkv, tokens):
    """The DONOR weapon's own display name for item_type_name (user: the subtext should read
    "Hammerfists" / "Assault Rifle" / "Lead Pipe", not the generic class name): a TF2C-localised
    token when it resolves, else a literal; None when the donor has no usable name."""
    cands = []
    nm = dkv.get("name")
    if src.startswith("tf2classic") and isinstance(nm, str) and " " in nm.strip() or (
            isinstance(nm, str) and src.startswith("tf2classic") and nm[:1].isupper() and nm[1:2].islower()):
        cands.append(nm)                                      # b4 "name" is the display name
    cands.append(dkv.get("item_name"))
    for n in cands:
        if not isinstance(n, str) or not n.strip():
            continue
        n = re.sub(r"\s*\((presplit|beta|beta \d|b\d|4rdm|4dm|old|classic)\)\s*$", "", n.strip(), flags=re.I)
        if n.startswith("#"):
            if n[1:].lower() in tokens:
                txt = tokens[n[1:].lower()]
                if not _MERC_WORD.search(txt) and not txt.strip().startswith("%"):
                    return n
                continue
            stem = re.sub(r"^#?TF_(Weapon_|Unique_)?", "", n[1:] if n.startswith("#") else n, flags=re.I)
            n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem).replace("_", " ").strip()
            if not n or n.isupper():
                continue
        if _MERC_WORD.search(n) or n.upper().startswith(("TF_", "CARD:", "SET BONUS")):
            continue
        return n
    return None


_KILLICONS = None


def known_killicons():
    """Kill-icon names the 5205 client can draw (pipeline.known_killicons on the installed game)."""
    global _KILLICONS
    if _KILLICONS is None:
        import pipeline
        import vfs as VFS
        _KILLICONS = pipeline.known_killicons(VFS.VFS(), pipeline.Q_SERVER_ROOT)
    return _KILLICONS


_TC_ICONS = None


def _model_stem(path):
    b = os.path.splitext(os.path.basename((path or "").replace("\\", "/")))[0].lower()
    return re.sub(r"_[0-9a-f]{8}$", "", b)


def tf2cc_model_icons():
    """Normalised model stem (no folder, no hash suffix) -> kill icon of the installed tf2cc item
    using that model (tf2cc renames staged models with a hash, e.g. v_stengun_4rdm_ef55bb78)."""
    global _TC_ICONS
    if _TC_ICONS is None:
        from generate import AF_SCHEMA, load_schema
        _TC_ICONS = {}
        for k, it in load_schema(AF_SCHEMA).get("items").blocks():
            if k.isdigit() and int(k) >= 30000 and it.get("model_player") and it.get("item_iconname"):
                _TC_ICONS.setdefault(_model_stem(it.get("model_player")), it.get("item_iconname"))
    return _TC_ICONS


def donor_killicon(dkv, known=None, model=None):
    """The kill icon of the weapon the item's MODEL comes from (user 2026-11-16: "reference the
    killicons of the donor models' originals"; 2026-11-20: "even if stock model donors, use the
    proper donor killicon, eg the Knee-Tickler is a medic melee using the bonesaw killicon but its
    model is the fire axe"). A CustomSlop item's item_class is not always the donor's (taunt fix:
    the class's own melee, saxxy for multi-class melee), and the engine's default kill icon follows
    the item_class - so the donor's icon must be explicit:
      1. the donor's own item_iconname (drawable ones only: pipeline.Ctx drops the rest);
      2. stock donors without one: the icon the engine draws for the donor's own weapon class,
         i.e. its item_class minus tf_weapon_ / tf2c_weapon_ (tf_weapon_fireaxe -> fireaxe), when
         the client has that death-notice icon; old Merc / beta models first take the icon of the
         installed tf2cc item that uses the same model (matched without tf2cc's hash suffix). Projectile launchers have none (the projectile's
         icon is drawn, e.g. tf_projectile_rocket) and keep the engine default.
    None = leave item_iconname unset."""
    ic = dkv.get("item_iconname")
    if ic:
        return ic
    known = known_killicons() if known is None else known
    tc = tf2cc_model_icons().get(_model_stem(model or dkv.get("model_player"))) if (model or dkv.get("model_player")) else None
    if tc and tc.lower() in known:
        return tc                              # the old Merc weapon's own icon (Sten -> tf2cc_merc_stengun_v1)
    stem = re.sub(r"^tf2?c?_weapon_", "", (dkv.get("item_class") or "").lower())
    return stem if stem and stem in known else None


def _with_killicon(it, dkv):
    ic = donor_killicon(dkv)
    if not ic or it.get("item_iconname") == ic:
        return it
    return kv.KV([(k, v) for k, v in it.pairs if k.lower() != "item_iconname"] + [("item_iconname", ic)])


def _is_merc(classes):
    return any(str(c).lower() in ("mercenary", "merc") for c in classes)


def sanitize(it, src, classes):
    """Copy of donor KV `it` without Merc/tf2cc-only keys (unless the item is for the Mercenary)."""
    if _is_merc(classes):
        return _with_killicon(it, it)
    tf2cc = src in TF2CC_SRCS
    out = kv.KV()
    for k, v in it.pairs:
        kl = k.lower()
        if kl == "static_attrs" and isinstance(v, kv.KV):
            keep = [(a, b) for a, b in v.pairs if a.lower() not in MERC_STATIC and not _TF2CC_REF.search(str(b))]
            if keep:
                out.add(k, kv.KV(keep))
            continue
        if kl.startswith("visuals") and isinstance(v, kv.KV):
            keep = []
            for a, b in v.pairs:
                al = a.lower()
                if al == "animation_replacement" and isinstance(b, kv.KV) and \
                        (tf2cc or any(_TF2CC_REF.search(str(x)) for _, x in b.pairs)):
                    continue                              # Merc player-model animations
                if isinstance(b, str) and (_TF2CC_REF.search(b) or (tf2cc and not b.startswith("customslop."))):
                    continue                              # tf2cc sound scripts / tracers / particles
                if isinstance(b, kv.KV) and tf2cc:
                    continue
                keep.append((a, b))
            if keep:
                out.add(k, kv.KV(keep))
            continue
        if kl == "tags":
            if isinstance(v, kv.KV) and [t.lower() for t, _ in v.pairs] == ["customslop"]:
                out.add(k, v)                            # CustomSlop's own tag; donor tags never
            continue
        # The kill icon is the donor's own (user, 2026-11-16: "reference the killicons of the donor
        # models' originals", e.g. the OF rocket launcher's): keep item_iconname for every donor,
        # and make it explicit for stock donors too (donor_killicon). The log name stays tf2cc-only.
        if kl == "item_logname" and tf2cc:
            continue
        if isinstance(v, str) and kl not in ("model_player", "model_world", "item_iconname") and _TF2CC_REF.search(v):
            continue
        out.add(k, v)
    return _with_killicon(out, it)


def _walk(node, path=()):
    for k, v in node.pairs:
        if isinstance(v, kv.KV):
            yield from _walk(v, path + (k,))
        else:
            yield path + (k,), v


def label_check(fragment_text, tokens):
    """Errors for CustomSlop items in `fragment_text` ('"<id>" { ... }' blocks)."""
    root = kv.parse('"x"\n{\n' + fragment_text + '\n}\n')[0].get("x")
    errs = []
    for k, it in root.blocks():
        ubc = it.get("used_by_classes")
        merc = _is_merc([c for c, _ in ubc.pairs] if isinstance(ubc, kv.KV) else [])
        itn = it.get("item_type_name")
        if not itn:
            errs.append("%s: no item_type_name" % k)
        elif itn.startswith("#") and itn[1:].lower() not in tokens:
            errs.append("%s: item_type_name %s is not localised by TF2C" % (k, itn))
        elif not merc and _MERC_WORD.search(tokens.get(itn[1:].lower(), "") if itn.startswith("#") else itn):
            errs.append("%s: Mercenary item_type_name on a non-Merc item" % k)
        if merc:
            continue
        for path, v in _walk(it):
            if path[-1].lower() in MERC_STATIC:
                errs.append("%s: Merc-only static attr %s" % (k, path[-1]))
            elif _TF2CC_REF.search(str(v)) and path[-1].lower() not in ("model_player", "model_world", "item_iconname"):
                errs.append("%s: tf2cc/Merc-only value %s = %s" % (k, "/".join(path), v))
            elif path[-1].lower() in ("model_player", "model_world") and "tf2cc" in str(v).lower():
                errs.append("%s: model depends on tf2cc content: %s" % (k, v))
        tags = it.get("tags")
        if isinstance(tags, kv.KV) and [t.lower() for t, _ in tags.pairs] != ["customslop"]:
            errs.append("%s: tags other than customslop: %s" % (k, [t for t, _ in tags.pairs]))
    return errs
