"""
slide_layout.py  --  decide what goes on each slide, independent of any output.

Turns lyrics text + a config into a plain description of the song's slides:
sections, and per slide the stacked text rows (text, font, size), the text box,
vertical alignment and the title. Nothing here knows about ProPresenter; the
.pro writer (make_pro.py) and the HTML preview (preview.py) both draw from
layout_song(), so they always agree.

    song = layout_song(text, load_config())    # a plain dict, see layout_song

THE LYRICS FORMAT

SECTIONS: start each part with a tag on its own line. Each becomes a named,
coloured group in ProPresenter:

    [Verse 1]
    Amazing grace how sweet the sound

    [Chorus]
    My chains are gone

    [Bridge | #8800cc]      <- optional explicit colour (#hex or r,g,b)
    You alone

Colours come from the name (Verse=blue, Chorus=red, Bridge=purple, Intro=olive,
...) unless given after a '|'. Only standard ProPresenter group tags (Verse,
Chorus, Bridge, Pre-Chorus, Intro, Outro, Tag, ...) become slides; typos such as
[Chrous] are corrected first, and any other tag ([youtube], [ccli], ...) is
skipped. With no tags at all, the whole text becomes one group.

SONG TITLE: a [Title] section ([标题] and [歌名] work too; @title / Title: /
标题： lines are also accepted). It is shown small on every slide, bottom-right
by default (config: title size / align / margins), and names the document.

TRANSLATIONS + PINYIN: put the translation after a bar on the lyric line
(| or full-width ｜ and similar).
    Chinese line  -> PINYIN (automatic, ALL CAPS) on top, the Chinese, then
                     the translation below.          求你使我们合一 | Breng ons samen
    Dutch/English -> the line, then its Chinese translation below.
                                                     Wij brengen U lof | 我们向你献上赞美
Pinyin needs `pip install pypinyin` (skipped if not installed).

PAGING / LINE BREAKS:
  - Default: one lyric line per slide.
  - A line that is just `//` starts a new slide; lines between them share one.
  - `//` inside a line breaks it there (for long lines).

FONTS / SIZES / OUTLINE / MARGINS / TITLE live in config.yaml (see
config.template.yaml, or `pp-make --init-config`): one font for Chinese and one
for Latin text, sizes per kind of line, white text with a black outline.
"""

import os, sys, re

# shared deterministic tag handling (works as a script and when installed)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _tags

# Optional: pinyin generation for Chinese lyrics (pip install pypinyin)
try:
    from pypinyin import pinyin as _pinyin, Style as _PyStyle
    _HAS_PYPINYIN = True
except Exception:
    _HAS_PYPINYIN = False


# ---------------------------------------------------------------------------
# Configuration, fonts, parsing, paging, rows
# ---------------------------------------------------------------------------
# Fonts that come with every Mac, by the name used in config.yaml.
# Value: (PostScript name ProPresenter's RTF needs, family name).
# A name not in this list is used as-is (for a font you installed yourself).
FONT_CATALOG = {
    "chinese": {
        "PingFang SC":          ("PingFangSC-Regular",  "PingFang SC"),
        "PingFang SC Medium":   ("PingFangSC-Medium",   "PingFang SC"),
        "PingFang SC Semibold": ("PingFangSC-Semibold", "PingFang SC"),
        "PingFang TC":          ("PingFangTC-Regular",  "PingFang TC"),
        "PingFang TC Medium":   ("PingFangTC-Medium",   "PingFang TC"),
        "PingFang TC Semibold": ("PingFangTC-Semibold", "PingFang TC"),
        "Heiti SC":             ("STHeitiSC-Medium",    "Heiti SC"),
        "Heiti TC":             ("STHeitiTC-Medium",    "Heiti TC"),
        "Songti SC":            ("STSongti-SC-Regular", "Songti SC"),
        "Songti SC Bold":       ("STSongti-SC-Bold",    "Songti SC"),
        "Songti TC":            ("STSongti-TC-Regular", "Songti TC"),
        "Songti TC Bold":       ("STSongti-TC-Bold",    "Songti TC"),
        "Hiragino Sans GB":     ("HiraginoSansGB-W3",   "Hiragino Sans GB"),
        "Hiragino Sans GB W6":  ("HiraginoSansGB-W6",   "Hiragino Sans GB"),
    },
    "latin": {
        "Helvetica Neue":        ("HelveticaNeue",        "Helvetica Neue"),
        "Helvetica Neue Medium": ("HelveticaNeue-Medium", "Helvetica Neue"),
        "Helvetica Neue Bold":   ("HelveticaNeue-Bold",   "Helvetica Neue"),
        "Helvetica":             ("Helvetica",            "Helvetica"),
        "Helvetica Bold":        ("Helvetica-Bold",       "Helvetica"),
        "Arial":                 ("ArialMT",              "Arial"),
        "Arial Bold":            ("Arial-BoldMT",         "Arial"),
        "Avenir Next":           ("AvenirNext-Regular",   "Avenir Next"),
        "Avenir Next Demi Bold": ("AvenirNext-DemiBold",  "Avenir Next"),
        "Avenir Next Bold":      ("AvenirNext-Bold",      "Avenir Next"),
        "Futura":                ("Futura-Medium",        "Futura"),
        "Gill Sans":             ("GillSans",             "Gill Sans"),
        "Optima":                ("Optima-Regular",       "Optima"),
        "Georgia":               ("Georgia",              "Georgia"),
        "Times New Roman":       ("TimesNewRomanPSMT",    "Times New Roman"),
        "Verdana":               ("Verdana",              "Verdana"),
        "Trebuchet MS":          ("TrebuchetMS",          "Trebuchet MS"),
    },
}


# Which font (chinese / latin) each text tier uses, unless the tier sets its own.
_TIER_KIND = {
    ("chinese", "pinyin"): "latin",
    ("chinese", "primary"): "chinese",
    ("chinese", "translation"): "latin",    # e.g. the Dutch translation
    ("latin", "primary"): "latin",
    ("latin", "translation"): "chinese",    # the Chinese translation
    ("title",): "latin",                    # a Chinese title uses the Chinese font
}


def font_names(name, kind):
    """(PostScript name, family) for a font given by its config.yaml name.
    Accepts catalog names (any case) and PostScript names; anything else is
    used as-is for both (a font you installed yourself)."""
    want = str(name).strip().lower()
    for k in [kind] + [x for x in FONT_CATALOG if x != kind]:
        for key, val in FONT_CATALOG[k].items():
            if want in (key.lower(), val[0].lower()):
                return val
    return str(name).strip(), str(name).strip()


def resolve_fonts(cfg):
    """Return a copy of cfg where every text tier has "font" and "family".

    Tiers that already set "font" (older config files) keep it; the others get
    the font from the "fonts" section (chinese / latin)."""
    import copy
    cfg = copy.deepcopy(cfg)
    fonts = cfg.get("fonts") or {}
    for path, kind in _TIER_KIND.items():
        tier = cfg
        for k in path:
            tier = tier.setdefault(k, {})
        if not tier.get("font"):
            name = fonts.get(kind) or DEFAULT_CONFIG["fonts"][kind]
            tier["font"], tier["family"] = font_names(name, kind)
        elif not tier.get("family"):
            tier["family"] = font_names(tier["font"], kind)[1]
    cfg["_cjk_font"] = font_names(fonts.get("chinese") or DEFAULT_CONFIG["fonts"]["chinese"],
                                  "chinese")
    return cfg


# Each tier is {"size": pt} plus, optionally, its own "font" (PostScript name)
# and "family"; without them the tier uses the "fonts" section (see resolve_fonts).
DEFAULT_CONFIG = {
    "slide":      {"width": 1920, "height": 1080},
    "text_color": [255, 255, 255],                 # white
    "stroke":     {"width": 6, "color": [0, 0, 0]}, # outline on ALL text (0 = off)
    "translation_gap": 70,     # blank space (pt) between a lyric and its translation
    # keep text this far (px) from each slide edge; per-side
    "margins": {"left": 96, "right": 96, "top": 54, "bottom": 54},
    "vertical_align": "middle",   # where lyric text sits: top | middle | bottom
    # chinese: all Chinese text; latin: pinyin, Dutch/English text and the title
    "fonts": {"chinese": "PingFang SC", "latin": "Helvetica Neue"},
    "chinese": {   # when the MAIN lyric line is Chinese
        "pinyin":      {"size": 65},
        "primary":     {"size": 120},
        "translation": {"size": 80},
    },
    "latin": {     # when the MAIN lyric line is Dutch / English
        "primary":     {"size": 110},
        "translation": {"size": 95},
    },
    "title": {"size": 70,
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
    header_re = re.compile(r"^\s*[\[\u3010](.+?)[\]\u3011]\s*$")  # ASCII [] or full-width 【】
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


# Default font used for any text box that contains CJK characters.
CJK_FONT_NAME = "PingFangSC-Regular"


CJK_FONT_FAMILY = "PingFang SC"


def pick_font(text, latin_name, latin_family, cjk_font=None):
    """Use the Chinese font if the text has CJK glyphs, else the given Latin font."""
    if has_cjk(text):
        return cjk_font or (CJK_FONT_NAME, CJK_FONT_FAMILY)
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
    is_cjk = has_cjk(text) if cjk is None else cjk
    if not is_cjk:                       # Latin row -> ，。！？（） etc. become ASCII
        text = normalize_latin_punct(text)
    return {"text": text, "font": tier["font"], "family": tier["family"],
            "size": tier["size"], "cjk": is_cjk}


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


def has_cjk(s):
    """True if the string contains actual CJK / Japanese / Korean characters.
    Full-width punctuation (e.g. the Chinese comma ，U+FF0C) does NOT count, so a
    Dutch/English line with a stray full-width mark stays non-Chinese."""
    for ch in s:
        o = ord(ch)
        if (0x4E00 <= o <= 0x9FFF          # CJK Unified Ideographs (Han)
                or 0x3400 <= o <= 0x4DBF       # CJK Extension A
                or 0xF900 <= o <= 0xFAFF       # CJK Compatibility Ideographs
                or 0x3040 <= o <= 0x30FF       # Hiragana + Katakana
                or 0xAC00 <= o <= 0xD7A3       # Hangul syllables
                or 0x20000 <= o <= 0x2FA1F):   # CJK ideographs, supplementary planes
            return True
    return False


def normalize_latin_punct(s):
    """Convert full-width CJK punctuation/letters to their ASCII equivalents.
    Applied only to non-Chinese (Latin) rows, so Chinese text keeps ，。、 etc."""
    out = []
    for ch in s:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:        # fullwidth ! \" # ... ~  ->  ASCII 0x21-0x7E
            out.append(chr(o - 0xFEE0))
        elif ch == "\u3000":             # ideographic space -> normal space
            out.append(" ")
        elif ch == "\u3001":             # 、 -> ,
            out.append(",")
        elif ch == "\u3002":             # 。 -> .
            out.append(".")
        else:
            out.append(ch)
    return "".join(out)


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
# Whole-song layout
# ---------------------------------------------------------------------------

def lyric_box(cfg):
    """(x, y, w, h) of the lyric text box: the slide minus the margins."""
    slide_w = float(cfg["slide"]["width"]); slide_h = float(cfg["slide"]["height"])
    mgn = cfg.get("margins", {})
    # per-side margins; fall back to x/y (symmetric) then 0 for back-compat
    mx = float(mgn.get("x", 0)); my = float(mgn.get("y", 0))
    ml = float(mgn.get("left",   mx))
    mr = float(mgn.get("right",  mx))
    mt = float(mgn.get("top",    my))
    mb = float(mgn.get("bottom", my))
    return (ml, mt, slide_w - ml - mr, slide_h - mt - mb)


def layout_song(text, cfg, *, group_name="Lyrics", footer_title=None):
    """Lay out a song. Returns a plain dict (no output format involved):

    {"title": str|None, "notes": [str],          # notes = tag fixes / skipped tags
     "cfg": resolved config,                      # fonts filled in for every tier
     "slide_size": (w, h), "text_color": [r,g,b], "stroke": {...},
     "sections": [{"name", "color": (r,g,b) 0-1,
                   "slides": [{"rows": [{text, font, family, size, cjk}],
                               "box": (x,y,w,h) | None, "valign": top|middle|bottom,
                               "title": {text, font, family, size, box, align} | None}]}]}
    """
    notes = []
    # fix typo'd standard tags FIRST (so [Chrous] -> [Chorus] is kept, not skipped)
    text, tag_warnings = _tags.correct_tags(text)
    notes.extend(tag_warnings)
    # title can come from: footer_title (CLI) > [Title] section > @title directive
    directive_title, text = parse_title(text)
    section_title, sections, skipped = parse_sections(text, default_name=group_name)
    for nm in skipped:
        notes.append("skipping non-standard section [%s] "
                     "(not a ProPresenter group tag)" % nm)
    title = footer_title or section_title or directive_title

    cfg = resolve_fonts(cfg)
    slide_w = float(cfg["slide"]["width"]); slide_h = float(cfg["slide"]["height"])
    tcfg = cfg["title"]
    valign = str(cfg.get("vertical_align", "middle")).lower()
    if valign not in ("top", "middle", "bottom"):
        valign = "middle"
    box = lyric_box(cfg)

    title_info = None
    if title:
        # a CJK title needs a font with the glyphs
        tfont, tfamily = pick_font(title, tcfg["font"], tcfg["family"], cfg["_cjk_font"])
        h = tcfg["size"] * 2.2
        x = tcfg["left_margin"]
        w = slide_w - tcfg["left_margin"] - tcfg["right_margin"]
        title_info = {"text": title, "font": tfont, "family": tfamily,
                      "size": tcfg["size"], "align": tcfg["align"],
                      "box": (x, slide_h - h - tcfg["bottom_margin"], w, h)}

    out_sections = []
    for sec in sections:
        slides = []
        for page_lines in paginate(sec["lines"], cfg["markers"]["page_break"]):
            rows = build_page_rows(page_lines, cfg)
            slides.append({"rows": rows, "box": box if rows else None,
                           "valign": valign, "title": title_info})
        out_sections.append({"name": sec["name"],
                             "color": tuple(sec["color"] if sec["color"]
                                            else group_color(sec["name"])),
                             "slides": slides})

    return {"title": title, "notes": notes, "cfg": cfg,
            "slide_size": (slide_w, slide_h), "text_color": cfg["text_color"],
            "stroke": cfg["stroke"], "sections": out_sections}
