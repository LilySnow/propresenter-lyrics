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
# Configuration and slide layout live in slide_layout.py (no ProPresenter code
# there). They are imported here so make_pro.<name> keeps working.
# ---------------------------------------------------------------------------
import slide_layout
from slide_layout import (  # noqa: F401  (re-exported)
    _HAS_PYPINYIN, FONT_CATALOG, _TIER_KIND, font_names, resolve_fonts,
    DEFAULT_CONFIG, _deep_merge, _read_config_file, load_config,
    split_linebreaks, paginate, chunk_lines, GROUP_COLORS, group_color,
    parse_color, TITLE_SECTION_NAMES, parse_sections, CJK_FONT_NAME,
    CJK_FONT_FAMILY, pick_font, pinyin_line, DEFAULT_SEPS, split_pair, _row,
    _spacer_row, build_page_rows, has_cjk, normalize_latin_punct, parse_title,
    lyric_box, layout_song)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_uuid(target):
    """Fill a rv.data.UUID message with a fresh random uuid."""
    target.string = str(uuid.uuid4())


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
    cfg = resolve_fonts(cfg)
    rows = build_page_rows(page_lines, cfg)
    valign = str(cfg.get("vertical_align", "middle")).lower()
    return _add_rows_element(base, rows, lyric_box(cfg), valign, cfg)


def _add_rows_element(base, rows, box, valign, cfg):
    """Write one laid-out text box (stacked rows) into a slide."""
    if not rows:
        return None
    color = cfg["text_color"]; stroke = cfg["stroke"]
    base_row = max(rows, key=lambda r: r["size"])     # biggest tier = element default

    sl_el = base.elements.add()
    sl_el.info = 2
    gel = sl_el.element
    new_uuid(gel.uuid)
    gel.name = "TextElement"
    gel.opacity = 1.0
    gel.bounds.origin.x, gel.bounds.origin.y = box[0], box[1]
    gel.bounds.size.width, gel.bounds.size.height = box[2], box[3]
    set_rect_path(gel.path)

    if valign not in ("top", "middle", "bottom"):
        valign = "middle"

    txt = gel.text
    txt.rtf_data = make_multitier_rtf(rows, color, stroke, align="center")
    txt.vertical_alignment = getattr(txt, "VERTICAL_ALIGNMENT_" + valign.upper())
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


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_presentation(name, text, cfg, *, group_name="Lyrics", footer_title=None):
    """Lay out the lyrics (slide_layout.layout_song) and write a Presentation.
    Notes about tags (typo fixes, skipped sections) go to stderr."""
    song = layout_song(text, cfg, group_name=group_name, footer_title=footer_title)
    for n in song["notes"]:
        sys.stderr.write("note: %s\n" % n)
    return write_presentation(song, name)


def write_presentation(song, name=None):
    """Turn a laid-out song (from slide_layout.layout_song) into a Presentation."""
    cfg = song["cfg"]
    title = song["title"]
    if title and (name is None or name == "Generated Song"):
        name = title
    slide_w, slide_h = song["slide_size"]
    color = song["text_color"]; stroke = song["stroke"]

    p = pres_pb2.Presentation()
    p.name = name or "Untitled"
    new_uuid(p.uuid)
    ai = p.application_info
    ai.application = appinfo_pb2.ApplicationInfo.APPLICATION_PROPRESENTER
    ai.platform = appinfo_pb2.ApplicationInfo.PLATFORM_MACOS
    ai.application_version.major_version = 7

    for sec in song["sections"]:
        sec_cue_ids = []
        for sl in sec["slides"]:
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

            _add_rows_element(base, sl["rows"], sl["box"], sl["valign"], cfg)

            t = sl["title"]
            if t:
                add_text_element(
                    base, [t["text"]], font_pt=t["size"], font_name=t["font"],
                    font_family=t["family"], color_rgb=color, stroke=stroke,
                    bounds=t["box"], align=t["align"], valign="bottom")

            sec_cue_ids.append(cue.uuid.string)

        cg = p.cue_groups.add()
        new_uuid(cg.group.uuid)
        cg.group.name = sec["name"]
        set_color(cg.group.color, *sec["color"])
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
    raw = raw.lstrip("\ufeff")   # strip a leading UTF-8 BOM if the editor added one
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
