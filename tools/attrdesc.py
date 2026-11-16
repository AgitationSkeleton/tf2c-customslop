"""TF2-style attribute description lines (text + colour role) from a schema's attribute definitions.

Follows TF2's CEconItemDescription rules:
  value_is_percentage           -> (v - 1) * 100
  value_is_inverted_percentage  -> (1 - v) * 100
  value_is_additive             -> v
  value_is_additive_percentage  -> v * 100
  value_is_or                   -> v
the number replaces %s1 in the localised description_string (rounded like TF2: integers unless
the value has a fractional part that matters); hidden attributes and attributes without a
description string produce no line; effect_type picks the colour role
(positive = blue, negative = red, neutral = cream).
"""
import re

ROLE = {"positive": "positive", "negative": "negative", "neutral": "neutral"}


def fmt_number(x):
    if abs(x - round(x)) < 0.05:
        return str(int(round(x)))
    return ("%.1f" % x).rstrip("0").rstrip(".")


def value_for(fmt, v):
    v = float(v)
    if fmt == "value_is_percentage":
        return (v - 1.0) * 100.0
    if fmt == "value_is_inverted_percentage":
        return (1.0 - v) * 100.0
    if fmt == "value_is_additive_percentage":
        return v * 100.0
    return v


def line(defn, value, loc):
    """defn: dict(name, desc_token|desc_text, fmt, effect, hidden). -> (text, role) or None"""
    if defn.get("hidden"):
        return None
    text = defn.get("desc_text")
    if not text and defn.get("desc_token"):
        text = loc.get(defn["desc_token"], None)
        if text is None or text.startswith("#"):
            return None
    if not text:
        return None
    if "%s1" in text:
        try:
            n = value_for(defn.get("fmt"), value)
        except (TypeError, ValueError):
            n = None
        text = text.replace("%s1", fmt_number(n) if n is not None else str(value))
    text = text.replace("%%", "%")
    return text, ROLE.get(defn.get("effect") or "neutral", "neutral")


def item_lines(attr_values, defs_by_name, loc):
    """attr_values: list of (attribute name, value) in schema order."""
    out = []
    for name, value in attr_values:
        d = defs_by_name.get(name.lower())
        if d:
            l = line(d, value, loc)
            if l:
                out.append(l)
    return out


def defs_from_schema(items_game_kv):
    out = {}
    for _, a in items_game_kv.get("attributes").blocks():
        nm = a.get("name")
        if not nm:
            continue
        out[nm.lower()] = dict(name=nm, desc_token=a.get("description_string"), fmt=a.get("description_format"),
                               effect=a.get("effect_type"), hidden=a.get("hidden") == "1")
    return out


def sort_lines(lines):
    """TF2 lists positive attribute lines, then negative, then neutral (stable within a group)."""
    order = {"positive": 0, "negative": 1, "neutral": 2}
    return sorted(lines, key=lambda l: order.get(l[1], 2))
