#!/usr/bin/env python3
"""
make_pro.py  --  Generate a ProPresenter 7 (.pro) presentation from plain text,
with full control over FONT SIZE and LINES-PER-SLIDE.

Requires the compiled protobuf modules (the *_pb2.py files) from
greyshirtguy/ProPresenter7-Proto on the import path. Compile them once with:

    git clone https://github.com/greyshirtguy/ProPresenter7-Proto.git
    cp -r "ProPresenter7-Proto/Proto 19beta" pp_proto
    pip install protobuf grpcio-tools
    cd pp_proto && python -m grpc_tools.protoc -I. --python_out=../gen *.proto

Then drop this file in the same folder as the generated *_pb2.py files.

The message path that holds slide text is:
    Presentation
      .cues[i]                                  -> one entry == one SLIDE
        .actions[j].slide.presentation.base_slide
          .elements[k].element.text.rtf_data    -> the text, as RTF bytes

Font size is an RTF code:  \fsN  where N = point_size * 2  (half-points).

GROUPS: mark sections in your text file with [Header] lines and each becomes a
named, coloured group in ProPresenter:

    [Verse 1]
    Amazing grace how sweet the sound
    That saved a wretch like me

    [Chorus]
    My chains are gone

    [Bridge | #8800cc]      <- optional explicit colour (#hex or r,g,b)
    You alone

Colours are auto-assigned from the name (Verse=blue, Chorus=red, Bridge=purple,
Intro=olive, ...) unless you give one after a '|'. With no [headers] at all the
whole file becomes a single group.

SONG TITLE: mark it with a [Title] section (same bracket style as groups). It is
placed small in the bottom-left of every slide and used as the document name:

    [Title]
    使我们合一

    [Verse 1]
    ...

[标题] and [歌名] work too. (Also still accepted: @title / Title: / 标题： lines.)
Footer size is set with --title-size (default 50pt). CJK text (in the title or
the lyrics) automatically uses a Chinese-capable font (PingFang SC).

TRANSLATIONS + PINYIN: put the translation after a '|' on each lyric line.
    Chinese primary  ->  PINYIN (auto, ALL CAPS) on top, 中文 at 100pt,
                         the translation below at 70pt.
        求你使我们合一 | Breng ons samen
    Dutch/English primary -> primary at 100pt, Chinese translation below at 90pt
        Wij brengen U lof | 我们向你献上赞美
Pinyin needs `pip install pypinyin` (skipped automatically if not installed).

PAGING / LINE BREAKS:
  - Default: one lyric line per page.
  - A standalone `//` line forces a PAGE break (lines between breaks share a page).
  - A `//` inside a line forces a visual LINE break there (for long lines).

FONTS / SIZES / STROKE / TITLE all live in config.yaml (edit that, not the code):
  Chinese lines -> pinyin 65 / 中文 120 / translation 80
  Dutch/English -> primary 105 / Chinese translation 95
  Title 70 (bottom-right), 6px black stroke on all text, white fill.
  Pass a different file with --config myconfig.yaml.
"""

import sys, re, uuid

# Optional: pinyin generation for Chinese lyrics (pip install pypinyin)
try:
    from pypinyin import pinyin as _pinyin, Style as _PyStyle
    _HAS_PYPINYIN = True
except Exception:
    _HAS_PYPINYIN = False

# --- locate the compiled proto modules (*_pb2.py) ---------------------------
# Look in a 'proto' subfolder next to this script first, then next to it, then
# an optional $PROPRESENTER_PROTO dir. This lets you keep make_pro.py in a tidy
# folder while the 115 generated *_pb2.py files live in ./proto.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
for _p in (_os.path.join(_HERE, "proto"), _HERE, _os.environ.get("PROPRESENTER_PROTO", "")):
    if _p and _os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# --- compiled proto modules ---
import presentation_pb2 as pres_pb2
import applicationInfo_pb2 as appinfo_pb2
import action_pb2
import graphicsData_pb2
import color_pb2

# shared deterministic tag handling (typo fix + standard-tag sets)
import _tags

# ---------------------------------------------------------------------------
# Configuration (all easily-tweakable settings live here / in config.yaml)
# ---------------------------------------------------------------------------
# Each tier is {"font": <rtf/postscript name>, "family": <display name>, "size": pt}.
DEFAULT_CONFIG = {
    "slide":      {"width": 1920, "height": 1080},
    "text_color": [255, 255, 255],                 # white
    "stroke":     {"width": 6, "color": [0, 0, 0]}, # outline on ALL text (0 = off)
    "translation_gap": 20,     # blank space (pt) between a lyric and its translation
    "margins": {"x": 96, "y": 54},   # keep text this far (px) from the slide edges
    "chinese": {   # when the MAIN lyric line is Chinese
        "pinyin":      {"font": "HelveticaNeue",     "family": "Helvetica Neue", "size": 65},
        "primary":     {"font": "PingFangSC-Regular","family": "PingFang SC",    "size": 120},
        "translation": {"font": "HelveticaNeue",     "family": "Helvetica Neue", "size": 80},
    },
    "latin": {     # when the MAIN lyric line is Dutch / English
        "primary":     {"font": "HelveticaNeue",     "family": "Helvetica Neue", "size": 110},
        "translation": {"font": "PingFangSC-Regular","family": "PingFang SC",    "size": 95},
    },
    "title": {"font": "HelveticaNeue", "family": "Helvetica Neue", "size": 70,
              "align": "right", "left_margin": 50, "right_margin": 110,
              "bottom_margin": 20},
    "markers": {"page_break": "//", "line_break": "//",
                "translation_sep": "|｜∣│"},  # any of these splits lyric | translation
}


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_config_file(path):
    import json
    if path.endswith((".yaml", ".yml")):
        import yaml
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_config(path=None):
    """Return DEFAULT_CONFIG merged with a user config, searched in order:
    1) explicit `path`, 2) ./config.{yaml,yml,json} in the current directory,
    3) ~/.config/propresenter-lyrics/config.{yaml,yml,json}. First one found
    wins; if none exist, the built-in defaults are used."""
    import os
    candidates = []
    if path:
        candidates.append(path)
    for d in (os.getcwd(), os.path.expanduser("~/.config/propresenter-lyrics")):
        for ext in ("yaml", "yml", "json"):
            candidates.append(os.path.join(d, "config." + ext))
    for cand in candidates:
        if cand and os.path.exists(cand):
            return _deep_merge(DEFAULT_CONFIG, _read_config_file(cand))
    return DEFAULT_CONFIG


def split_linebreaks(s, marker="//"):
    """Split one line into visual sub-lines at an in-line '//'. 'a // b' -> ['a','b']."""
    return [p.strip() for p in s.split(marker) if p.strip()]


def paginate(section_lines, page_marker="//"):
    """Split a section's lines into pages.

    Default: one line per page. If the section contains a standalone '//' line,
    that switches to explicit paging: lines between '//' (or blank) lines share
    a page.
    """
    has_marker = any(l.strip() == page_marker for l in section_lines)
    pages, cur = [], []
    if has_marker:
        for l in section_lines:
            if l.strip() == page_marker or l.strip() == "":
                if cur:
                    pages.append(cur); cur = []
            else:
                cur.append(l)
        if cur:
            pages.append(cur)
    else:
        for l in section_lines:
            if l.strip():
                pages.append([l])
    return pages

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_uuid(target):
    """Fill a rv.data.UUID message with a fresh random uuid."""
    target.string = str(uuid.uuid4())


def chunk_lines(lines, lines_per_slide):
    """Split a list of raw text lines into slides; each slide is a list of lines.

    A blank line acts as a forced slide break (common for verse/chorus gaps).
    Otherwise lines are grouped `lines_per_slide` at a time.
    """
    slides, current = [], []
    for raw in lines:
        line = raw.rstrip()
        if line == "":                       # blank line -> break the slide
            if current:
                slides.append(current)
                current = []
            continue
        current.append(line)
        if len(current) >= lines_per_slide:
            slides.append(current)
            current = []
    if current:
        slides.append(current)
    return slides


# ProPresenter's standard group label colours (matched from a real file).
# Keyed by the first word of the group name, lower-cased.
GROUP_COLORS = {
    "intro":   (0.70, 0.65, 0.14),
    "verse":   (0.00, 0.47, 0.80),
    "chorus":  (0.80, 0.00, 0.31),
    "prechorus": (0.90, 0.35, 0.13),
    "bridge":  (0.46, 0.00, 0.80),
    "tag":     (0.13, 0.59, 0.95),
    "outro":   (0.40, 0.40, 0.40),
    "ending":  (0.40, 0.40, 0.40),
}


def group_color(name):
    """Pick a colour for a group from its name; grey if unknown."""
    key = re.sub(r"[^a-z]", "", name.split()[0].lower()) if name.split() else ""
    return GROUP_COLORS.get(key, (0.40, 0.40, 0.40))


def parse_color(spec):
    """Parse '#RRGGBB' or 'r,g,b' (0-1 floats or 0-255 ints) -> (r,g,b) floats."""
    spec = spec.strip()
    if spec.startswith("#") and len(spec) == 7:
        return tuple(int(spec[i:i+2], 16) / 255.0 for i in (1, 3, 5))
    parts = [float(x) for x in spec.split(",")]
    if any(x > 1 for x in parts):
        parts = [x / 255.0 for x in parts]
    return tuple(parts[:3])


TITLE_SECTION_NAMES = _tags.TITLE_TAGS


# Standard ProPresenter group tags come from _tags.GROUP_TAGS. Only sections
# whose name matches one (by first word) become slides; other tags are metadata.
def parse_sections(text, default_name="Lyrics", group_tags=None):
    """Split text into sections by '[Group Name]' header lines.

    A section named [Title] / [标题] / [歌名] is special: its text is taken as the
    song title (not turned into slides). Only sections whose tag is a standard
    ProPresenter group tag (see DEFAULT_GROUP_TAGS) become slides; any other tag
    is metadata and skipped. Un-tagged content before the first header is always
    kept. Returns (title, sections, skipped_names)."""
    group_tags = group_tags or _tags.GROUP_TAGS
    header_re = re.compile(r"^\s*\[(.+?)\]\s*$")
    title = None
    sections, skipped = [], []
    cur = {"name": default_name, "color": None, "lines": [], "explicit": False}

    def flush(section):
        nonlocal title
        if not any(l.strip() for l in section["lines"]):
            return
        nm = section["name"].strip().lower()
        first = nm.split()[0] if nm.split() else nm
        if nm in TITLE_SECTION_NAMES:
            if title is None:                       # first title wins
                title = next(l.strip() for l in section["lines"] if l.strip())
        elif not section["explicit"]:
            sections.append(section)                # un-tagged default content
        elif first in group_tags or nm in group_tags:
            sections.append(section)                # standard group tag
        else:
            skipped.append(section["name"].strip())  # metadata -> skip

    for raw in text.splitlines():
        m = header_re.match(raw)
        if m:
            flush(cur)
            header = m.group(1)
            if "|" in header:
                nm, col = header.split("|", 1)
                color = parse_color(col)
            else:
                nm, color = header, None
            cur = {"name": nm.strip(), "color": color, "lines": [], "explicit": True}
        else:
            cur["lines"].append(raw)
    flush(cur)
    return title, sections, skipped


def rtf_escape(s):
    """Escape a single line of text for RTF (handles unicode incl. CJK)."""
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif o < 128:
            out.append(ch)
        else:
            # RTF \uN? : N is a signed 16-bit int; values >32767 wrap negative.
            code = o - 65536 if o > 32767 else o
            out.append("\\u%d?" % code)
    return "".join(out)


# Default font used for any text box that contains CJK characters.
CJK_FONT_NAME = "PingFangSC-Regular"
CJK_FONT_FAMILY = "PingFang SC"


def pick_font(text, latin_name, latin_family):
    """Use a CJK font if the text has CJK glyphs, else the requested Latin font."""
    if has_cjk(text):
        return CJK_FONT_NAME, CJK_FONT_FAMILY
    return latin_name, latin_family


def pinyin_line(text):
    """ALL-CAPS toneless pinyin, e.g. 使我们合一 -> 'SHI WO MEN HE YI'.
    Returns None if pypinyin is unavailable.

    Reverence pronouns are read as their ordinary counterparts for pinyin only:
    祢 -> NI (not MI), 祂 -> TA. The displayed character is unchanged.
    """
    if not _HAS_PYPINYIN:
        return None
    for rev, plain in (("祢", "你"), ("祂", "他")):
        text = text.replace(rev, plain)
    syl = _pinyin(text, style=_PyStyle.NORMAL, errors="ignore")
    return " ".join(w[0] for w in syl if w and w[0]).upper().strip() or None


DEFAULT_SEPS = "|｜∣│"      # ascii pipe, full-width pipe, divides, box-vertical


def split_pair(raw, seps=DEFAULT_SEPS):
    """Split a lyric line into (primary, translation) at the first separator char.
    Accepts several 'vertical bar' characters, not just the ascii '|'."""
    idxs = [raw.find(s) for s in seps if raw.find(s) != -1]
    if idxs:
        i = min(idxs)
        return raw[:i].strip(), raw[i + 1:].strip()
    return raw.strip(), None


def _row(text, tier, cjk=None):
    return {"text": text, "font": tier["font"], "family": tier["family"],
            "size": tier["size"], "cjk": has_cjk(text) if cjk is None else cjk}


def _spacer_row(gap, cfg):
    """A blank row (non-breaking space) that pushes the translation down by ~gap pt."""
    f = cfg["latin"]["primary"]
    return {"text": "\u00a0", "font": f["font"], "family": f["family"],
            "size": gap, "cjk": False}


def build_page_rows(page_lines, cfg):
    """Turn a page's source lines into stacked rows using the config tiers.

    Each source line 'primary <sep> translation' becomes:
      Chinese primary -> PINYIN / 中文 (per // sub-line) then translation sub-lines.
      Latin primary   -> primary sub-lines then Chinese-translation sub-lines.
    In-line '//' splits a long line into visual sub-lines. Returns list of rows.
    """
    lb = cfg["markers"]["line_break"]
    seps = cfg["markers"].get("translation_sep", DEFAULT_SEPS)
    if isinstance(seps, (list, tuple)):
        seps = "".join(seps)
    gap = cfg.get("translation_gap", 0)
    rows = []
    for raw in page_lines:
        primary, trans = split_pair(raw, seps)
        if not primary:
            continue
        if has_cjk(primary):                          # Chinese scenario
            t = cfg["chinese"]
            for sub in split_linebreaks(primary, lb):
                py = pinyin_line(sub)
                if py:
                    rows.append(_row(py, t["pinyin"], cjk=False))
                rows.append(_row(sub, t["primary"], cjk=True))
            if trans:
                if gap:
                    rows.append(_spacer_row(gap, cfg))
                for sub in split_linebreaks(trans, lb):
                    rows.append(_row(sub, t["translation"]))
        else:                                         # Dutch / English scenario
            t = cfg["latin"]
            for sub in split_linebreaks(primary, lb):
                rows.append(_row(sub, t["primary"], cjk=False))
            if trans:
                if gap:
                    rows.append(_spacer_row(gap, cfg))
                for sub in split_linebreaks(trans, lb):
                    rows.append(_row(sub, t["translation"]))
    return rows


def _stroke_tokens(stroke):
    """RTF stroke run tokens for a given stroke config, or '' if disabled.
    Uses colour index 2 (added to the colortbl by the RTF builders)."""
    w = stroke.get("width", 0)
    if not w:
        return ""
    return "\\strokec2\\strokewidth%d" % int(round(-20 * abs(w)))  # neg = fill+outline


def make_multitier_rtf(rows, color_rgb, stroke, align="center"):
    """RTF for a stack of rows, each with its own font + size, plus a text stroke."""
    tr, tg, tb = color_rgb
    sc = stroke.get("color", [0, 0, 0])
    qcode = {"center": "\\qc", "left": "\\ql", "right": "\\qr"}.get(align, "\\qc")

    fonts = []
    for r in rows:
        if r["font"] not in fonts:
            fonts.append(r["font"])
    ftbl = "".join(
        "\\f%d\\fnil\\fcharset%d %s;" % (
            i, 134 if any(x["cjk"] and x["font"] == fn for x in rows) else 0, fn)
        for i, fn in enumerate(fonts))
    fidx = {fn: i for i, fn in enumerate(fonts)}
    stok = _stroke_tokens(stroke)

    parts = [
        "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2639",
        "{\\fonttbl%s}" % ftbl,
        "{\\colortbl;\\red%d\\green%d\\blue%d;\\red%d\\green%d\\blue%d;}"
        % (tr, tg, tb, sc[0], sc[1], sc[2]),
        "{\\*\\expandedcolortbl;;;}",
        "\\pard\\pardirnatural%s\\partightenfactor0" % qcode,
    ]
    body = []
    for i, r in enumerate(rows):
        half = int(round(r["size"] * 2))
        nl = "\\\n" if i < len(rows) - 1 else ""
        body.append("\\f%d\\fs%d%s \\cf1 %s%s"
                     % (fidx[r["font"]], half, stok, rtf_escape(r["text"]), nl))
    parts.append("".join(body) + "}")
    return "\n".join(parts).encode("utf-8")


def _apply_text_attrs(txt, *, font_name, font_family, size, color_rgb, stroke,
                      align="center"):
    """Set the proto text attributes PP renders from (font, colour, stroke, align)."""
    r, g, b = color_rgb
    txt.attributes.font.name = font_name
    txt.attributes.font.family = font_family
    txt.attributes.font.size = float(size)
    txt.attributes.text_solid_fill.red = r / 255.0
    txt.attributes.text_solid_fill.green = g / 255.0
    txt.attributes.text_solid_fill.blue = b / 255.0
    txt.attributes.text_solid_fill.alpha = 1.0
    txt.attributes.paragraph_style.alignment = getattr(
        graphicsData_pb2.Graphics.Text.Attributes, _ALIGN_ENUM[align])
    txt.attributes.paragraph_style.line_height_multiple = 1.0
    if stroke.get("width", 0):
        sc = stroke.get("color", [0, 0, 0])
        txt.attributes.stroke_width = -abs(float(stroke["width"]))  # neg = fill+outline
        txt.attributes.stroke_color.red = sc[0] / 255.0 if sc[0] > 1 else sc[0]
        txt.attributes.stroke_color.green = sc[1] / 255.0 if sc[1] > 1 else sc[1]
        txt.attributes.stroke_color.blue = sc[2] / 255.0 if sc[2] > 1 else sc[2]
        txt.attributes.stroke_color.alpha = 1.0


def add_lyric_element(base, page_lines, cfg):
    """Add the main multi-tier lyric text box for one page, per the config."""
    rows = build_page_rows(page_lines, cfg)
    if not rows:
        return None
    slide_w = float(cfg["slide"]["width"]); slide_h = float(cfg["slide"]["height"])
    color = cfg["text_color"]; stroke = cfg["stroke"]
    base_row = max(rows, key=lambda r: r["size"])     # biggest tier = element default

    sl_el = base.elements.add()
    sl_el.info = 2
    gel = sl_el.element
    new_uuid(gel.uuid)
    gel.name = "TextElement"
    gel.opacity = 1.0
    mgn = cfg.get("margins", {})
    mx = float(mgn.get("x", 0)); my = float(mgn.get("y", 0))
    gel.bounds.origin.x = mx
    gel.bounds.origin.y = my
    gel.bounds.size.width = slide_w - 2 * mx
    gel.bounds.size.height = slide_h - 2 * my
    set_rect_path(gel.path)

    txt = gel.text
    txt.rtf_data = make_multitier_rtf(rows, color, stroke, align="center")
    txt.vertical_alignment = txt.VERTICAL_ALIGNMENT_MIDDLE
    _apply_text_attrs(txt, font_name=base_row["font"], font_family=base_row["family"],
                      size=base_row["size"], color_rgb=color, stroke=stroke,
                      align="center")
    return gel


def make_rtf(lines, font_pt, font_name="HelveticaNeue", color_rgb=(255, 255, 255),
             align="center", stroke=None):
    """Build RTF bytes for one single-tier text box (e.g. the title footer)."""
    half = int(round(font_pt * 2))
    r, g, b = color_rgb
    stroke = stroke or {"width": 0}
    sc = stroke.get("color", [0, 0, 0])
    stok = _stroke_tokens(stroke)
    qcode = {"center": "\\qc", "left": "\\ql", "right": "\\qr"}.get(align, "\\qc")
    body = "\\\n".join(rtf_escape(ln) for ln in lines)
    return (
        "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2639\n"
        "{\\fonttbl\\f0\\fnil\\fcharset0 %s;}\n"
        "{\\colortbl;\\red%d\\green%d\\blue%d;\\red%d\\green%d\\blue%d;}\n"
        "{\\*\\expandedcolortbl;;;}\n"
        "\\pard\\pardirnatural%s\\partightenfactor0\n"
        "\\f0\\fs%d%s \\cf1 %s}"
        % (font_name, r, g, b, sc[0], sc[1], sc[2], qcode, half, stok, body)
    ).encode("utf-8")


def set_color(c, r, g, b, a=1.0):
    c.red, c.green, c.blue, c.alpha = r, g, b, a


def set_rect_path(path):
    """Give an element a rectangular shape path (unit square, scaled by bounds).

    ProPresenter needs this geometry to actually draw the element; without it
    the text box has no drawable area and renders nothing.
    """
    path.closed = True
    for (x, y) in [(0, 0), (1, 0), (1, 1), (0, 1)]:
        bp = path.points.add()
        bp.point.x = x; bp.point.y = y
        bp.q0.x = x;    bp.q0.y = y
        bp.q1.x = x;    bp.q1.y = y
    path.shape.type = path.shape.TYPE_RECTANGLE


_ALIGN_ENUM = {
    "center": "ALIGNMENT_CENTER",
    "left":   "ALIGNMENT_LEFT",
    "right":  "ALIGNMENT_RIGHT",
}


def has_cjk(s):
    """True if the string contains Chinese/Japanese/Korean characters."""
    return any(
        "\u3000" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7a3"
        or "\uff00" <= ch <= "\uffef"
        for ch in s
    )


def add_text_element(base, lines, *, font_pt, font_name, font_family,
                     color_rgb, bounds, align="center", valign="middle",
                     stroke=None):
    """Add one single-tier text box to a slide. bounds = (x, y, w, h)."""
    stroke = stroke or {"width": 0}
    sl_el = base.elements.add()
    sl_el.info = 2  # INFO_IS_TEXT_ELEMENT
    gel = sl_el.element
    new_uuid(gel.uuid)
    gel.name = "TextElement"
    gel.opacity = 1.0
    gel.bounds.origin.x, gel.bounds.origin.y = bounds[0], bounds[1]
    gel.bounds.size.width, gel.bounds.size.height = bounds[2], bounds[3]
    set_rect_path(gel.path)

    txt = gel.text
    txt.rtf_data = make_rtf(lines, font_pt, font_name, color_rgb, align, stroke)
    txt.vertical_alignment = getattr(txt, "VERTICAL_ALIGNMENT_" + valign.upper())
    _apply_text_attrs(txt, font_name=font_name, font_family=font_family,
                      size=font_pt, color_rgb=color_rgb, stroke=stroke, align=align)
    return gel


def parse_title(text):
    """Pull a title directive out of the text and return (title, cleaned_text).

    Recognised (case-insensitive), anywhere in the file, on its own line:
        @title Amazing Grace
        Title: Amazing Grace
        标题：使我们合一        (full-width or half-width colon)
    The directive line is removed so it never becomes a slide.
    """
    title = None
    kept = []
    pat = re.compile(r"^\s*(?:@title|title\s*[:：]|标题\s*[:：])\s*(.+?)\s*$",
                     re.IGNORECASE)
    for raw in text.splitlines():
        m = pat.match(raw)
        if m and title is None:
            title = m.group(1).strip()
        else:
            kept.append(raw)
    return title, "\n".join(kept)


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_presentation(name, text, cfg, *, group_name="Lyrics", footer_title=None):
    # title can come from: footer_title (CLI) > [Title] section > @title directive
    # fix typo'd standard tags FIRST (so [Chrous] -> [Chorus] is kept, not skipped)
    text, tag_warnings = _tags.correct_tags(text)
    for w in tag_warnings:
        sys.stderr.write("note: %s\n" % w)
    directive_title, text = parse_title(text)
    section_title, sections, skipped = parse_sections(text, default_name=group_name)
    for nm in skipped:
        sys.stderr.write("note: skipping non-standard section [%s] "
                         "(not a ProPresenter group tag)\n" % nm)
    title = footer_title or section_title or directive_title
    if title and (name is None or name == "Generated Song"):
        name = title

    slide_w = float(cfg["slide"]["width"]); slide_h = float(cfg["slide"]["height"])
    color = cfg["text_color"]; stroke = cfg["stroke"]
    tcfg = cfg["title"]
    page_marker = cfg["markers"]["page_break"]

    p = pres_pb2.Presentation()
    p.name = name or "Untitled"
    new_uuid(p.uuid)
    ai = p.application_info
    ai.application = appinfo_pb2.ApplicationInfo.APPLICATION_PROPRESENTER
    ai.platform = appinfo_pb2.ApplicationInfo.PLATFORM_MACOS
    ai.application_version.major_version = 7

    # a CJK title needs a font with the glyphs
    title_font, title_family = pick_font(title or "", tcfg["font"], tcfg["family"])

    for sec in sections:
        sec_cue_ids = []
        for page_lines in paginate(sec["lines"], page_marker):
            cue = p.cues.add()
            new_uuid(cue.uuid)
            cue.isEnabled = True

            action = cue.actions.add()
            new_uuid(action.uuid)
            action.isEnabled = True
            action.type = action_pb2.Action.ACTION_TYPE_PRESENTATION_SLIDE

            base = action.slide.presentation.base_slide
            new_uuid(base.uuid)
            base.size.width = slide_w
            base.size.height = slide_h
            base.draws_background_color = False

            add_lyric_element(base, page_lines, cfg)

            if title:
                h = tcfg["size"] * 2.2
                x = tcfg["left_margin"]
                w = slide_w - tcfg["left_margin"] - tcfg["right_margin"]
                add_text_element(
                    base, [title], font_pt=tcfg["size"], font_name=title_font,
                    font_family=title_family, color_rgb=color, stroke=stroke,
                    bounds=(x, slide_h - h - tcfg["bottom_margin"], w, h),
                    align=tcfg["align"], valign="bottom")

            sec_cue_ids.append(cue.uuid.string)

        cg = p.cue_groups.add()
        new_uuid(cg.group.uuid)
        cg.group.name = sec["name"]
        col = sec["color"] if sec["color"] else group_color(sec["name"])
        set_color(cg.group.color, *col)
        for sid in sec_cue_ids:
            cg.cue_identifiers.add().string = sid

    return p


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse, os
    ap = argparse.ArgumentParser(description="Generate a ProPresenter 7 .pro from lyrics text")
    ap.add_argument("textfile", nargs="?", default=None,
                    help="lyrics file. Omit (or use '-') to read from stdin / a pipe.")
    ap.add_argument("-o", "--out", default="output.pro")
    ap.add_argument("-n", "--name", default="Generated Song")
    ap.add_argument("--title", default=None, help="Song title footer (overrides [Title] in the file)")
    ap.add_argument("--config", default=None,
                    help="config file (YAML or JSON) for fonts/sizes/stroke/title")
    ap.add_argument("--init-config", nargs="?", const="", default=None,
                    metavar="PATH",
                    help="write a commented config.yaml you can edit, then exit "
                         "(default: ~/.config/propresenter-lyrics/config.yaml)")
    args = ap.parse_args()

    if args.init_config is not None:
        import shutil
        dest = os.path.expanduser(
            args.init_config or "~/.config/propresenter-lyrics/config.yaml")
        template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "config.template.yaml")
        d = os.path.dirname(dest)
        if d:
            os.makedirs(d, exist_ok=True)
        shutil.copyfile(template, dest)
        print("Wrote editable config to %s" % dest)
        return

    cfg = load_config(args.config)

    textfile = args.textfile
    if textfile in (None, "-"):
        if textfile is None and sys.stdin.isatty():
            ap.error("no lyrics file given and nothing piped to stdin")
        raw = sys.stdin.read()
    else:
        raw = open(os.path.expanduser(textfile), encoding="utf-8").read()
    if not raw.strip():
        ap.error("no lyrics content (input was empty)")
    out_path = os.path.expanduser(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    p = build_presentation(args.name, raw, cfg, footer_title=args.title)
    if not _HAS_PYPINYIN:
        sys.stderr.write("NOTE: pypinyin not installed -> no pinyin added. "
                         "Run: pip install pypinyin\n")
    with open(out_path, "wb") as fh:
        fh.write(p.SerializeToString())
    print("Wrote %s : %d slides" % (out_path, len(p.cues)))


if __name__ == "__main__":
    main()
