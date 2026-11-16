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


def _is_merc(classes):
    return any(str(c).lower() in ("mercenary", "merc") for c in classes)


def sanitize(it, src, classes):
    """Copy of donor KV `it` without Merc/tf2cc-only keys (unless the item is for the Mercenary)."""
    if _is_merc(classes):
        return it
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
        if kl in ("item_logname", "item_iconname") and tf2cc:
            continue
        if isinstance(v, str) and kl not in ("model_player", "model_world") and _TF2CC_REF.search(v):
            continue
        out.add(k, v)
    return out


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
            elif _TF2CC_REF.search(str(v)) and path[-1].lower() not in ("model_player", "model_world"):
                errs.append("%s: tf2cc/Merc-only value %s = %s" % (k, "/".join(path), v))
            elif path[-1].lower() in ("model_player", "model_world") and "tf2cc" in str(v).lower():
                errs.append("%s: model depends on tf2cc content: %s" % (k, v))
        tags = it.get("tags")
        if isinstance(tags, kv.KV) and [t.lower() for t, _ in tags.pairs] != ["customslop"]:
            errs.append("%s: tags other than customslop: %s" % (k, [t for t, _ in tags.pairs]))
    return errs
