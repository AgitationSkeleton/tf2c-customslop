"""CustomSlop weapon names + descriptions (v2: many templates, large pools, similarity guard).

make_name(rng, used, info=None) -> str
make_description(rng, traits, ctx, used=None, info=None, name=None) -> str

`used` is either a plain set of lower-cased names (old callers) or a History (a set subclass that
also remembers each name's template / head word and every description's form + fragment ids).
History.from_catalogue(weapons, root) seeds it from the catalogue so tonight's weapons are never
similar to anything CustomSlop has made before.

`info` (optional) lets names/descriptions follow the weapon: dict(item_class, fam, slot,
classes=[...], attrs=[{cls, value}...], wrong=<class or None>).

Similarity guard (names): a candidate is rejected if, against any of the last WINDOW names, it
  - is the same name (checked against the WHOLE history, ever),
  - shares any content word stem (so "Municipal Peashooter" vs "Mediocre Peashooter" is similar),
  - has token Jaccard >= 0.4 or character-trigram Jaccard >= 0.5,
  - uses the same template with the same head word,
and its template must not be one of the last TEMPLATE_COOLDOWN templates.
Descriptions: never the same text twice (whole history); against the last WINDOW descriptions no
shared fragment (each quip / review / warning / lore line ...), no shared 4-word shingle, content
Jaccard < 0.3, trigram Jaccard < 0.5; form not among the last FORM_COOLDOWN forms.
Retries are bounded; the guard relaxes in two steps, then a deterministic fallback is used.
"""
import json
import math
import os
import re
from collections import Counter

import descwords as DW
import namewords as NW

WINDOW = 60
TEMPLATE_COOLDOWN = 5
FORM_COOLDOWN = 3
NAME_MAX = 40
DESC_MAX = 200
TRIES = 300
STATS = Counter()     # which guard stage produced each name/description (namecheck.py reports it)

STOP = set("""the of and a an in on at to for with from by or but not no is it its it's this that be as
    mk mk. de le la el il der das don mon herr l'ami ye olde
    co inc corp jr sr""".split())
CLASS_WORDS = set(w.lower() for w in NW.CLASSES_ALL) | {"demo", "red", "blu", "grn", "ylw", "team"}
_TOK = re.compile(r"[a-z]+")
ROMANS = {"ii", "iv", "vi", "ix", "xi", "xx"}           # short numerals still count ("Mark IV" ~ "Mk. IV")


# ------------------------------------------------------------------------------------------ text utils
def tokens(s, extra_stop=()):
    """Content words; a hyphenated word also yields its joined form (Ka-Blam -> ka, blam, kablam)."""
    out = []
    for word in s.lower().replace("'s ", " ").split():
        parts = _TOK.findall(word)
        if len(parts) > 1:
            parts.append("".join(parts))
        for w in parts:
            if (len(w) < 3 and w not in ROMANS) or w in STOP or w in extra_stop:
                continue
            out.append(w)
    return out


def fold(w):
    """Letters only, sound-alike folded: 'Ka-Blam' == 'Kablam', 'Klonk' == 'Clonk'."""
    w = "".join(_TOK.findall(str(w).lower()))
    return w.replace("ph", "f").replace("ck", "k").replace("k", "c").replace("z", "s")


def stem(w):
    """Crude stem + sound-alike folding (Klonk ~ Clonk, Phizz ~ Fizz)."""
    if len(w) > 4 and w.endswith("s"):
        w = w[:-1]
    w = w.replace("ph", "f").replace("ck", "k").replace("k", "c").replace("z", "s")
    return w[:5]


def stems(s, extra_stop=()):
    """Word stems, plus the 4-letter ending of long words ("~nker") so Bonker ~ Clonker read alike."""
    out = set()
    for w in tokens(s, extra_stop):
        out.add(stem(w))
        if len(w) >= 7:
            out.add("~" + stem(w[-4:] if not w.endswith("s") else w[-5:-1]))
    return out


def trigrams(s):
    t = " ".join(_TOK.findall(s.lower()))
    t = re.sub(r"^the ", "", t)
    t = " %s " % t
    return {t[i:i + 3] for i in range(len(t) - 2)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def shingles(s, n=4):
    w = _TOK.findall(s.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def safe_text(s):
    """Plain ASCII, no characters that KeyValues / localisation / Discord markdown would mangle."""
    s = s.encode("ascii", "ignore").decode()
    for ch in '"%#*_`~{}\\\n\r\t':
        s = s.replace(ch, "")
    return re.sub(r"\s+", " ", s).strip()


def _norm(s):
    return " ".join(_TOK.findall(s.lower()))


# ------------------------------------------------------------------------------------------ history
class History(set):
    """Set of lower-cased names (drop-in for the old `used` set) plus template/description memory."""

    def __init__(self, names=()):
        super().__init__()
        self.names = []     # dicts: name, tid, head, stems, toks, tri
        self.descs = []     # dicts: text, norm, form, frags, stems, tri, sh
        for n in names:
            self.note_name(n)

    def note_name(self, name, tid=None, head=None):
        set.add(self, name.lower())
        self.names.append(dict(name=name, tid=tid, head=str(head or "").lower(), stems=stems(name),
                               toks=set(tokens(name)), tri=trigrams(name)))

    def note_desc(self, text, form=None, frags=(), name=""):
        st = stems(text, extra_stop=CLASS_WORDS | set(tokens(name)))
        self.descs.append(dict(text=text, norm=_norm(text), form=form, frags=set(frags), stems=st,
                               tri=trigrams(text), sh=shingles(text)))

    @classmethod
    def from_catalogue(cls, weapons, root=None):
        """weapons: catalogue dict defindex -> entry (name, dir). Reads each summary.json's description."""
        h = cls()
        items = weapons.values() if isinstance(weapons, dict) else weapons
        for w in sorted(items, key=lambda w: int(w.get("defindex", 0))):
            if not w.get("name"):
                continue
            h.note_name(w["name"])
            desc = w.get("description")
            if not desc and root and w.get("dir"):
                try:
                    with open(os.path.join(root, w["dir"], "summary.json")) as f:
                        desc = json.load(f).get("description")
                except (OSError, ValueError):
                    desc = None
            if desc:
                h.note_desc(desc, name=w["name"])
        return h


def _as_history(used):
    if isinstance(used, History):
        return used
    return History(sorted(used or ()))


# ------------------------------------------------------------------------------------------ weapon info
def kind_of(item_class, fam=None):
    ic = (item_class or "").lower()
    for keys, kind in ((("rocket",), "rocket"), (("aagun", "minigun", "heavyartillery"), "minigun"),
                       (("pipebomb", "grenade"), "grenade"), (("flaregun",), "flare"), (("flame",), "flame"),
                       (("scatter", "shotgun"), "shotgun"), (("pistol", "revolver"), "pistol"),
                       (("syringe", "nailgun"), "needle"), (("smg",), "smg"),
                       (("sniperrifle", "hunterrifle"), "rifle"), (("bow",), "bow"),
                       (("knife", "fireaxe", "bonesaw", "sword", "club", "axe"), "blade"),
                       (("bat", "bottle", "shovel", "wrench", "fists", "umbrella", "pan"), "blunt")):
        if any(k in ic for k in keys):
            return kind
    return {"melee": "blunt", "flame": "flame", "rocket": "rocket", "grenade": "grenade"}.get(fam or "", "generic")


THEMES = [
    ("fire", r"burn|ignite|afterburn|flame|fire_?dmg"),
    ("explosive", r"blast|explosion|radius|splash"),
    ("crit", r"crit"),
    ("firerate", r"postfiredelay|fire_?rate|attack_?speed"),
    ("reload", r"reload"),
    ("clip", r"clip"),
    ("ammo", r"ammo"),
    ("speed", r"move_?speed|speed_buff|jump|airdash|sprint"),
    ("health", r"health|heal|regen"),
    ("knockback", r"knockback|push|airblast"),
    ("defense", r"dmgtaken|resist|dmg_from|flinch"),
    ("accuracy", r"spread|accuracy"),
    ("mechanic", r"build|sentry|dispenser|teleport|cloak|backstab|disguise|medigun|uber|charge|shield|metal"),
    ("damage", r"dmg|damage|bleed|headshot"),
]


def stat_theme(attrs):
    """The flavour theme of the weapon's most extreme stat ('plain' when nothing stands out)."""
    best, bm = "plain", 0.0
    for a in attrs or ():
        c = str(a.get("cls") or a.get("name") or "").lower()
        if not c or c == "custom_projectile_model":
            continue
        theme = next((t for t, rx in THEMES if re.search(rx, c)), None)
        if not theme:
            continue
        try:
            v = float(a.get("value"))
            m = abs(math.log(v)) if 0 < v < 20 and v != 1 else 0.35
        except (TypeError, ValueError):
            m = 0.3
        if "customslop_ignite_self" in c:
            m = 2.0
        if m > bm:
            best, bm = theme, m
    return best


def _info(info):
    info = dict(info or {})
    classes = list(info.get("classes") or [])
    cls = classes[0] if classes else None
    kind = kind_of(info.get("item_class"), info.get("fam"))
    return dict(kind=kind, cls=cls, theme=stat_theme(info.get("attrs")), wrong=info.get("wrong"))


# ------------------------------------------------------------------------------------------ name templates
PLACE_PROPER = [p for p in NW.PLACE if not p.lower().startswith("the ")]


def _kn(r, x, generic_p=0.15):
    pool = NW.KIND_NOUN.get(x["kind"], NW.KIND_NOUN["generic"])
    return r.choice(NW.KIND_NOUN["generic"] if r.random() < generic_p else pool)


def _cls(r, x):
    return x["cls"] or r.choice(NW.CLASSES_ALL)


def t_adj_noun(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.ADJ), n), n


def t_adj_noun_bare(r, x):
    n = _kn(r, x)
    return "%s %s" % (r.choice(NW.ADJ), n), n


def t_agent(r, x):
    a = r.choice(NW.AGENT)
    return "The %s-%s" % (r.choice(NW.TARGET), a), a


def t_coin(r, x):
    root, suf = r.choice(NW.ROOT), r.choice(NW.SUFFIX_COIN)
    w = (root[:-1] if root[-1] == suf[0] else root) + suf
    return (w if r.random() < 0.5 else "The " + w), root


def t_lore_owner(r, x):
    n = _kn(r, x)
    return "%s's %s" % (r.choice(NW.LORE_OWNER), n), n


def t_first_adj(r, x):
    n = _kn(r, x)
    return "%s's %s %s" % (r.choice(NW.FIRST_NAME), r.choice(NW.ADJ), n), n


def t_relation(r, x):
    n = _kn(r, x)
    return "The %s's %s's %s" % (_cls(r, x), r.choice(NW.RELATION), n), n


def t_place(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(PLACE_PROPER), n), n


def t_corporate(r, x):
    b = r.choice(NW.BRAND_WORD) + r.choice(NW.PRODUCT_WORD)
    return "%s %s %s" % (r.choice(NW.MANUFACTURER), b, r.choice(NW.MODEL_TAG)), b


def t_model(r, x):
    n = _kn(r, x)
    code = "%s%d" % (r.choice("ABCDEFGHJKLMNPRSTVWXZ"), r.randint(2, 999))
    return "Model %s %s" % (code, n), n


def t_mil(r, x):
    nick = r.choice(NW.NICKNAME)
    pre = r.choice(NW.MIL_PREFIX)
    num = r.choice([str(r.randint(1, 99)), str(r.randint(1850, 1975)), "%d%s" % (r.randint(1, 40), r.choice("ABCDE"))])
    sep = "-" if pre in ("M", "XM", "T") else " "
    return "%s%s%s %s" % (pre, sep, num, nick), nick


def t_mark(r, x):
    n = _kn(r, x)
    rm = r.choice(NW.ROMAN)
    return ("%s Mk. %s" % (n, rm) if r.random() < 0.5 else "Mark %s %s" % (rm, n)), n


def t_alliter(r, x):
    n = r.choice(NW.KIND_NOUN.get(x["kind"], []) + NW.KIND_NOUN["generic"])
    adjs = [a for a in NW.ADJ + NW.JOKE_ADJ if a[0].lower() == n[0].lower()]
    if not adjs:
        return None
    return "The %s %s" % (r.choice(adjs), n), n


def t_rhyme(r, x):
    n = r.choice(NW.RHYME_NAMES)
    return ("The " + n if r.random() < 0.5 else n), n


# curated puns that only make sense on some weapon kinds (or stat themes)
_MELEE = {"blunt", "blade"}
_GUNS = set(NW.KIND_NOUN) - _MELEE - {"generic"}
PUN_RULES = [
    (r"\b(Bat|Club|Wrench|Shovel|Hammer|Dig|Grave)\b", {"blunt"}),
    (r"\b(Saw|Knife|Stab|Axe|Edge|Cut|Splitting)\b", {"blade"}),
    (r"\b(Gun|Barrel|Recoil|Trigger|Bullet|Clip|Magazine|Reload|Caliber|Shot|Spray|Blank|Shell|Lead|Ammo|Hit and Miss)\b",
     _GUNS),
    (r"\b(Rocket|Blast|Boom|Fallout|Splash|Fuse|Sticky|Pipe|Cannon|Bang)\b", {"rocket", "grenade", "flare", "minigun"}),
    (r"\b(Flame|Airblast|Heat|Smoke|Burn|Burnt|Toast|Flash|Hot)\b", {"flame", "flare", "fire"}),
]


def pun_fits(n, x):
    for rx, ok in PUN_RULES:
        if re.search(rx, n) and not ({x["kind"], x["theme"]} & ok):
            return False
    return True


def t_pun(r, x):
    n = r.choice(NW.PUN_NAMES)
    return (n, n) if pun_fits(n, x) else None


def t_phrase(r, x):
    n = r.choice(NW.PHRASE_NAMES)
    return n, n


def t_persona(r, x):
    n = r.choice(NW.PERSONA)
    return n, n


def t_acronym(r, x):
    n = r.choice(NW.ACRONYM_NAMES)
    return n, n


def t_sequel(r, x):
    n = _kn(r, x, 0.3)
    return r.choice(NW.SEQUEL_FORM).replace("{N}", n), n


def t_of(r, x):
    n = _kn(r, x)
    return "The %s %s" % (n, r.choice(NW.OF_PHRASE)), n


def t_long(r, x):
    n = _kn(r, x)
    a1, a2 = r.sample(NW.ADJ, 2)
    return "The %s %s %s of %s" % (a1, a2, n, r.choice(PLACE_PROPER)), n


def t_occupation(r, x):
    n = _kn(r, x)
    return "The %s's %s" % (r.choice(NW.OCCUPATION), n), n


def t_year(r, x):
    n = _kn(r, x)
    y = r.choice(NW.YEAR)
    return ("The %s %s" % (y, n) if r.random() < 0.5 else "%s Model %s" % (y, n)), n


def t_title(r, x):
    root = r.choice(NW.ROOT)
    return "%s %s%s" % (r.choice(NW.TITLE), root, r.choice(NW.SURNAME_TAIL)), root


def t_ono_noun(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.ONO), n), n


def t_ono(r, x):
    o = r.choice(NW.ONO)
    return (o + "!" if r.random() < 0.4 else "The " + o), o


def t_class_form(r, x):
    fl = NW.CLASS_FLAVOR.get(_cls(r, x)) or NW.CLASS_FLAVOR["Soldier"]
    form = r.choice(fl["forms"])
    n, f = _kn(r, x), r.choice(NW.HEAVY_FEMALE)
    return form.replace("{N}", n).replace("{F}", f), (f if "{F}" in form else n)


def t_class_adj(r, x):
    fl = NW.CLASS_FLAVOR.get(_cls(r, x)) or NW.CLASS_FLAVOR["Soldier"]
    n = _kn(r, x)
    return "The %s %s" % (r.choice(fl["adj"]), n), n


def t_foreign(r, x):
    n = _kn(r, x, 0.3).split("-")[0]
    g, lt = r.choice(NW.GERMAN_ROOT), r.choice(NW.LATIN_ROOT)
    form = r.choice(NW.FOREIGN_FORMS)
    head = g if "{G}" in form else lt if "{L}" in form else n
    return form.replace("{N}", n).replace("{G}", g).replace("{L}", lt), head


def t_material(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.MATERIAL), n), n


def t_number(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.NUMBER_PART), n), n


def t_animal(r, x):
    a = r.choice(NW.ANIMAL)
    return "The %s %s" % (r.choice(NW.ADJ), a), a


def t_animal_noun(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.ANIMAL), n), n


def t_house(r, x):
    h = r.choice(NW.HOUSE)
    return "The %s %s" % (r.choice(NW.JOKE_ADJ), h), h


def t_stat_adj(r, x):
    n = _kn(r, x)
    return "The %s %s" % (r.choice(NW.STAT_ADJ[x["theme"]]), n), n


def t_stat_of(r, x):
    n = _kn(r, x)
    return "The %s %s" % (n, r.choice(NW.STAT_OF[x["theme"]])), n


def t_noun_noun(r, x):
    n = _kn(r, x)
    if "-" in n:
        return None
    return "The %s-%s" % (n, r.choice([w for w in NW.HOUSE + NW.KIND_NOUN["generic"] if "-" not in w])), n


def t_one_word(r, x):
    w = r.choice([w for w in NW.KIND_NOUN.get(x["kind"], []) + NW.NICKNAME if "-" not in w])
    return w, w


def t_brand_short(r, x):
    n = _kn(r, x)
    return "The %s-%s" % (r.choice(NW.BRAND_WORD), n), n


# (id, weight, builder) - weights keep any single template well under 10% of rolls
NAME_TEMPLATES = [
    ("adj_noun", 4, t_adj_noun), ("adj_noun_bare", 2, t_adj_noun_bare), ("agent", 4, t_agent),
    ("coin", 3, t_coin), ("lore_owner", 3, t_lore_owner), ("first_adj", 2, t_first_adj),
    ("relation", 2, t_relation), ("place", 3, t_place), ("corporate", 2, t_corporate), ("model", 2, t_model),
    ("mil", 3, t_mil), ("mark", 2, t_mark), ("alliter", 3, t_alliter), ("rhyme", 2, t_rhyme),
    ("pun", 4, t_pun), ("phrase", 2, t_phrase), ("persona", 2, t_persona), ("acronym", 1, t_acronym),
    ("sequel", 2, t_sequel), ("of", 3, t_of), ("long", 1, t_long), ("occupation", 2, t_occupation),
    ("year", 2, t_year), ("title", 2, t_title), ("ono_noun", 2, t_ono_noun), ("ono", 1, t_ono),
    ("class_form", 4, t_class_form), ("class_adj", 3, t_class_adj), ("foreign", 2, t_foreign),
    ("material", 2, t_material), ("number", 2, t_number), ("animal", 2, t_animal),
    ("animal_noun", 2, t_animal_noun), ("house", 2, t_house), ("stat_adj", 3, t_stat_adj),
    ("stat_of", 2, t_stat_of), ("noun_noun", 1, t_noun_noun), ("one_word", 2, t_one_word),
    ("brand_short", 2, t_brand_short),
]


# shape limits per CAP_WINDOW rolls: no template more than its cap (default 2), and look-alike
# template families ("The X of Y", "The Adj Noun", possessives, model codes, curated) capped together
CAP_WINDOW = 50
NAME_CAP = dict(acronym=1, ono=1, long=1, noun_noun=1, house=1, rhyme=1, title=1, sequel=1, one_word=1,
                adj_noun_bare=1, phrase=1)
NAME_FAMILY = [({"of", "stat_of", "long", "sequel"}, 4),
               ({"adj_noun", "adj_noun_bare", "class_adj", "stat_adj", "material", "number", "alliter", "animal",
                 "place", "ono_noun", "animal_noun", "brand_short", "house"}, 16),
               ({"lore_owner", "first_adj", "relation", "occupation"}, 6),
               ({"corporate", "model", "mil", "mark", "year"}, 7),
               ({"pun", "phrase", "persona", "rhyme", "acronym"}, 7)]
DESC_CAP = dict(quip=8, warning=5, ad=5, review=3, lore=5, maker=4, stat=6, name=3, haiku=2, couplet=2,
                history=4, classified=2, steps=2, ingredients=3, quote=3, combo=6)


def _capped(recent_ids, caps, families=(), default=2):
    """Template/form ids that already hit their cap among recent_ids."""
    cnt = {}
    for i in recent_ids:
        cnt[i] = cnt.get(i, 0) + 1
    full = {i for i, n in cnt.items() if n >= caps.get(i, default)}
    for fam, cap in families:
        if sum(cnt.get(i, 0) for i in fam) >= cap:
            full |= fam
    return full


def _weighted(r, items, skip, soft=()):
    """Weighted pick of an id, avoiding `skip` and (if anything is left) `soft`."""
    pool = ([(it[0], it[1]) for it in items if it[0] not in skip and it[0] not in soft] or
            [(it[0], it[1]) for it in items if it[0] not in skip] or [(it[0], it[1]) for it in items])
    k = r.random() * sum(w for _, w in pool)
    for i, w in pool:
        k -= w
        if k <= 0:
            return i
    return pool[-1][0]


def name_similar(c, o, strict=True):
    """c/o: dicts with stems, toks, tri, tid, head. True if they read as 'similar'."""
    if strict and c["stems"] & o["stems"]:
        return True
    if c["tid"] and c["tid"] == o.get("tid") and c["head"] == o.get("head"):
        return True
    if c["head"] and fold(c["head"]) == fold(o.get("head") or ""):     # same head word, any template
        return True
    if jaccard(c["toks"], o["toks"]) >= 0.4:
        return True
    return jaccard(c["tri"], o["tri"]) >= 0.5


def make_name(rng, used, info=None):
    h = _as_history(used)
    x = _info(info)
    recent = h.names[-WINDOW:]
    cool = {n["tid"] for n in h.names[-TEMPLATE_COOLDOWN:] if n["tid"]}
    capped = _capped([n["tid"] for n in h.names[-CAP_WINDOW:] if n["tid"]], NAME_CAP, NAME_FAMILY)
    byid = {t[0]: t for t in NAME_TEMPLATES}
    for stage in ("strict", "loose", "min"):
        win = recent if stage != "min" else recent[-10:]
        for _ in range(TRIES):
            tid = _weighted(rng, NAME_TEMPLATES, cool if stage != "min" else (), capped)
            got = byid[tid][2](rng, x)
            if not got:
                continue
            nm, head = safe_text(got[0]), got[1]
            if not nm or len(nm) > NAME_MAX or nm.lower() in h:
                continue
            parts = [stem(w) for w in _TOK.findall(nm.lower()) if len(w) >= 3 and w not in STOP]
            if tid != "ono" and len(parts) != len(set(parts)):        # "Pipe-Dream-Bagpipe"
                continue
            c = dict(stems=stems(nm), toks=set(tokens(nm)), tri=trigrams(nm), tid=tid, head=str(head).lower())
            if any(name_similar(c, o, strict=(stage == "strict")) for o in win):
                continue
            STATS["name_" + stage] += 1
            return _accept_name(used, h, nm, tid, head)
    n = len(h.names) + 1
    while "prototype no. %d" % n in h:                          # deterministic fallback
        n += 1
    STATS["name_fallback"] += 1
    return _accept_name(used, h, "Prototype No. %d" % n, "fallback", "prototype")


def _accept_name(used, h, nm, tid, head):
    if h is used:
        h.note_name(nm, tid, head)
    elif used is not None:
        used.add(nm.lower())
    return nm


# ------------------------------------------------------------------------------------------ descriptions
GUN_WORDS = re.compile(r"(?i)\b(trigger|barrel|bullets?|magazine|reload\w*|recoil|scope|ammo\w*|ammunition|"
                       r"fired|fires|shots?|safety|clip|aim\w*|rockets)\b")


def plural(c):
    return {"Demoman": "Demomen"}.get(c, c + "s")


class _Filler:
    """Fills {slots}; records which pool entries were used as fragment ids."""

    def __init__(self, r, x, name, ctx):
        self.r, self.x, self.name = r, x, name
        self.frags = []
        self.cls = x["cls"] or r.choice(NW.CLASSES_ALL)
        self.other = r.choice([c for c in NW.CLASSES_ALL if c != self.cls])
        y = r.randint(1850, 1968)
        self.vals = {"Name": name or "it", "cls": self.cls, "other": self.other,
                     "clsP": plural(self.cls), "otherP": plural(self.other), "kind": DW.KIND_WORD[x["kind"]],
                     "Place": r.choice(PLACE_PROPER), "Team": r.choice(NW.TEAM), "Maker": r.choice(NW.MANUFACTURER),
                     "Year": str(y), "Year2": str(y + r.randint(1, 30)), "First": r.choice(NW.FIRST_NAME),
                     "Relation": r.choice(NW.RELATION).replace("-", " ").lower(),
                     "Occupation": r.choice(NW.OCCUPATION).replace("-", " ").lower(),
                     "Animal": r.choice(NW.ANIMAL).lower(), "House": r.choice(NW.HOUSE).replace("-", " ").lower(),
                     "Num": str(r.randint(2, 97)), "verbs": r.choice(DW.AD_VERBS),
                     "proj": ctx.get("proj") or "something", "wcls": ctx.get("cls") or "anyone"}

    def pick(self, tag, pool):
        for _ in range(12):                               # melee weapons have no trigger, barrel or bullets
            i = self.r.randrange(len(pool))
            if not (self.x["kind"] in _MELEE and GUN_WORDS.search(pool[i])):
                break
        self.frags.append("%s:%d" % (tag, i))
        return self.fill(pool[i])

    FRESH = {"Relation": lambda r: r.choice(NW.RELATION).replace("-", " ").lower(),
             "Occupation": lambda r: r.choice(NW.OCCUPATION).replace("-", " ").lower(),
             "Animal": lambda r: r.choice(NW.ANIMAL).lower(),
             "House": lambda r: r.choice(NW.HOUSE).replace("-", " ").lower(),
             "First": lambda r: r.choice(NW.FIRST_NAME)}

    def fill(self, s):
        nm = self.vals["Name"]
        if nm.lower().startswith("the "):                 # "the {Name}" + "The Thunk Hedgehog" -> one "The"
            s = re.sub(r"\b[Tt]he \{Name\}", "{Name}", s)
            s = re.sub(r"\b(one|this|a|my|your|every) \{Name\}", lambda m: m.group(1) + " " + nm[4:], s)
            s = re.sub(r"([a-z,:] )\{Name\}", lambda m: m.group(1) + "the " + nm[4:], s)
        seen = set()

        def sub(m):
            k = m.group(1)
            if k in self.FRESH and k in seen:             # a second {Relation} in one line is a different one
                return self.FRESH[k](self.r)
            seen.add(k)
            return self.vals.get(k, m.group(0))
        return re.sub(r"\{(\w+)\}", sub, s)


def _cap(s):
    return s[:1].upper() + s[1:]


def _end(s):
    s = s.strip()
    return s if s[-1:] in ".!?)" else s + "."


def d_quip(f):
    return f.pick("Q", DW.QUIPS)


def d_warning(f):
    return "%s %s" % (f.pick("WL", DW.WARN_LABEL), _cap(f.pick("W", DW.WARNINGS)))


def d_ad(f):
    return f.pick("AD", DW.AD_COPY)


def d_review(f):
    return "%s %s - %s" % (f.pick("RT", DW.RATING), f.pick("RV", DW.REVIEW_TEXT), _cap(f.pick("RW", DW.REVIEWER)))


def d_lore(f):
    return f.pick("LO" + f.cls[:3], DW.CLASS_LORE.get(f.cls) or DW.CLASS_LORE["Soldier"])


def d_maker(f):
    return f.pick("MK", DW.MAKER_NOTE)


def d_stat(f):
    s = f.pick("ST" + f.x["theme"][:4], DW.STAT_LINES[f.x["theme"]])
    if f.r.random() < 0.5:
        s = _end(s) + " " + f.pick("Q", DW.QUIPS)
    return s


def d_name(f):
    return f.pick("NM", DW.NAME_LINES) if f.name else None


def d_haiku(f):
    a, b = f.r.sample(range(len(DW.HAIKU5)), 2)
    f.frags += ["H5:%d" % a, "H5:%d" % b]
    return _cap("%s / %s / %s" % (f.fill(DW.HAIKU5[a]), f.pick("H7", DW.HAIKU7), f.fill(DW.HAIKU5[b])))


def d_couplet(f):
    return f.pick("CP", DW.COUPLETS)


def d_history(f):
    return f.pick("HI", DW.HISTORY)


def d_classified(f):
    return f.pick("CL", DW.CLASSIFIED)


def d_steps(f):
    idx = f.r.sample(range(len(DW.STEPS)), 3)
    f.frags += ["SP:%d" % i for i in idx]
    return " ".join("Step %d: %s." % (n + 1, _cap(f.fill(DW.STEPS[i]))) for n, i in enumerate(idx))


def d_ingredients(f):
    idx = f.r.sample(range(len(DW.INGREDIENTS)), 3)
    f.frags += ["IG:%d" % i for i in idx]
    a, b, c = (f.fill(DW.INGREDIENTS[i]) for i in idx)
    return "Ingredients: %s, %s and %s." % (a, b, c)


def d_quote(f):
    return "'%s' - %s" % (f.pick("QT", DW.QUOTES), _cap(f.pick("SK", DW.SPEAKER)))


def d_combo(f):
    first = f.r.choice([d_stat, d_history, d_maker, d_lore])(f)
    return "%s %s" % (_end(first), f.r.choice([d_warning, d_quip])(f))


DESC_FORMS = [
    ("quip", 4, d_quip), ("warning", 3, d_warning), ("ad", 3, d_ad), ("review", 3, d_review),
    ("lore", 3, d_lore), ("maker", 2, d_maker), ("stat", 3, d_stat), ("name", 2, d_name),
    ("haiku", 1, d_haiku), ("couplet", 1, d_couplet), ("history", 2, d_history),
    ("classified", 1, d_classified), ("steps", 1, d_steps), ("ingredients", 2, d_ingredients),
    ("quote", 2, d_quote), ("combo", 2, d_combo),
]


def desc_similar(c, o, strict=True):
    if c["norm"] == o.get("norm"):
        return True
    if strict and (c["frags"] & o["frags"] or c["sh"] & o["sh"]):
        return True
    if jaccard(c["stems"], o["stems"]) >= 0.3:
        return True
    return jaccard(c["tri"], o["tri"]) >= 0.5


def make_description(rng, traits, ctx, used=None, info=None, name=None):
    h = used if isinstance(used, History) else History()
    x = _info(info)
    ctx = dict(ctx or {})
    recent = h.descs[-WINDOW:]
    cool = {d["form"] for d in h.descs[-FORM_COOLDOWN:] if d["form"]}
    capped = _capped([d["form"] for d in h.descs[-CAP_WINDOW:] if d["form"]], DESC_CAP, default=3)
    ever = {d["norm"] for d in h.descs}
    byid = {t[0]: t for t in DESC_FORMS}
    nstop = CLASS_WORDS | set(tokens(name or ""))
    for stage in ("strict", "loose", "min"):
        win = recent if stage != "min" else recent[-10:]
        for _ in range(TRIES):
            f = _Filler(rng, x, name, ctx)
            tl = [f.pick("TR" + t[:4], DW.TRAIT_LINES[t]) for t in traits or () if t in DW.TRAIT_LINES]
            rng.shuffle(tl)
            form = _weighted(rng, DESC_FORMS, cool if stage != "min" else (), capped)
            body = byid[form][2](f)
            if not body:
                continue
            text = safe_text(" ".join(_end(s) for s in tl[:2] + [body]))
            if len(text) > DESC_MAX:
                continue
            c = dict(norm=_norm(text), frags=set(f.frags), sh=shingles(text), tri=trigrams(text),
                     stems=stems(text, extra_stop=nstop))
            if c["norm"] in ever or any(desc_similar(c, o, strict=(stage == "strict")) for o in win):
                continue
            h.note_desc(text, form, f.frags, name or "")
            STATS["desc_" + stage] += 1
            return text
    text = "Unit %d of a series nobody asked for." % (len(h.descs) + 1)   # deterministic fallback
    h.note_desc(text, "fallback", (), name or "")
    STATS["desc_fallback"] += 1
    return text


def combinations():
    """Rough size of the name space (main generated templates + curated names)."""
    kn = sum(len(v) for v in NW.KIND_NOUN.values()) // len(NW.KIND_NOUN)
    a = len(NW.ADJ)
    return (a * kn * 6 + len(NW.TARGET) * len(NW.AGENT) + len(NW.ROOT) * len(NW.SUFFIX_COIN) * 3 +
            len(NW.LORE_OWNER) * kn + len(NW.FIRST_NAME) * a * kn + len(PLACE_PROPER) * kn +
            len(NW.MANUFACTURER) * len(NW.BRAND_WORD) * len(NW.PRODUCT_WORD) * len(NW.MODEL_TAG) +
            len(NW.PUN_NAMES) + len(NW.RHYME_NAMES) + len(NW.PHRASE_NAMES) + len(NW.PERSONA))
