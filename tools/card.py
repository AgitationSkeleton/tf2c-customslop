"""TF2 item-info card renderer (Pillow), in the format of TF2's backpack/loadout item panel.

Fonts are loaded at runtime from the user's own TF2 install ("TF2 Build" = tf2build.ttf for the
name, "TF2 Secondary" = tf2secondary.ttf for everything else) and are never copied into the tool
or its outputs' repo. Search order: config "fonts_dir", then every Steam library's
"steamapps/common/Team Fortress 2/tf/resource" (libraryfolders.vdf), then known fallbacks.

Colours (TF2's ClientScheme; sampled from the reference images to within 1-2 levels):
  card bg 36,33,28 (#24211C)     icon box 61,54,46 (#3D362E)
  unique quality 255,215,0       item level/type 117,107,94
  positive 153,204,255           negative 255,64,64          neutral 235,226,202
"""
import os
import re

from PIL import Image, ImageDraw, ImageFont

BG = (36, 33, 28, 255)
BOX = (61, 54, 46, 255)
COL = {"name": (255, 215, 0), "level": (117, 107, 94), "positive": (153, 204, 255),
       "negative": (255, 64, 64), "neutral": (235, 226, 202)}
import cspaths as P

STEAM_DEFAULT = P.opt("steam_dir") or ""


def steam_libraries():
    libs = [STEAM_DEFAULT]
    vdf = os.path.join(STEAM_DEFAULT, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8").read())]
    return list(dict.fromkeys(libs))


def find_fonts(fonts_dir=None):
    dirs = [fonts_dir or P.opt("fonts_dir")]
    if P.opt("tf2_client_dir"):
        dirs.append(os.path.join(P.opt("tf2_client_dir"), "tf", "resource"))
    dirs += [os.path.join(l, "steamapps", "common", "Team Fortress 2", "tf", "resource") for l in steam_libraries()]
    for d in dirs:
        if not d:
            continue
        b, s = os.path.join(d, "tf2build.ttf"), os.path.join(d, "tf2secondary.ttf")
        if os.path.exists(b) and os.path.exists(s):
            return b, s
    raise FileNotFoundError("TF2 fonts not found: install TF2 or set fonts_dir to a folder with tf2build.ttf + tf2secondary.ttf")


def _rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def wrap(text, font, width, draw):
    out = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= width or not cur:
                cur = t
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


def render_card(name, type_line, lines, icon=None, width=560, scale=2, fonts=None, level=None, crisp=False):
    """name: item name (rendered uppercase); type_line: e.g. 'Level 15 Bat';
    lines: list of (text, role) with role in positive/negative/neutral; icon: PIL RGBA or None."""
    s = scale
    W = width * s
    fb, fs = fonts or find_fonts()
    # metrics measured on the 559 px wide reference (The Sandman)
    f_name = ImageFont.truetype(fb, 32 * s)
    f_level = ImageFont.truetype(fs, 26 * s)
    f_desc = ImageFont.truetype(fs, 26 * s)
    pad, box_w, box_h, top = 16 * s, 222 * s, 167 * s, 10 * s
    lh_desc = 40 * s     # Scorch Shot / Shiv references (the Sandman screenshot is tighter: 32)
    meas = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    name_lines = wrap(name.upper(), f_name, W - 2 * pad, meas)
    body = []
    for text, role in lines:
        for l in wrap(text, f_desc, W - 2 * pad, meas):
            body.append((l, role))
    y_name = top + box_h + 25 * s
    name_h = 40 * s * len(name_lines)
    y_level = y_name + name_h + 10 * s
    y_body = y_level + 45 * s
    H = y_body + lh_desc * len(body) + 22 * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _rounded(d, (0, 0, W - 1, H - 1), 14 * s, BG)
    bx0 = (W - box_w) // 2
    _rounded(d, (bx0, top, bx0 + box_w, top + box_h), 14 * s, BOX)
    if icon is not None:
        ic = icon.copy()
        bb = ic.getbbox()
        if bb:
            ic = ic.crop(bb)
        k = min((box_w * 0.82) / ic.width, (box_h * 0.78) / ic.height)
        if crisp:                                   # premultiplied area resize: no dark fringe
            import numpy as _np
            import srcshade as _SS
            ic = Image.fromarray(_SS.resize_premul(_np.asarray(ic.convert("RGBA")), (max(1, int(ic.width * k)), max(1, int(ic.height * k)))), "RGBA")
        else:
            ic = ic.resize((max(1, int(ic.width * k)), max(1, int(ic.height * k))), Image.LANCZOS)
        img.alpha_composite(ic, (bx0 + (box_w - ic.width) // 2, top + (box_h - ic.height) // 2))
    y = y_name
    for nl in name_lines:
        d.text((W / 2, y), nl, font=f_name, fill=COL["name"], anchor="mt")
        y += 40 * s
    d.text((W / 2, y_level), type_line, font=f_level, fill=COL["level"], anchor="mt")
    y = y_body
    for text, role in body:
        d.text((W / 2, y), text, font=f_desc, fill=COL.get(role, COL["neutral"]), anchor="mt")
        y += lh_desc
    return img
