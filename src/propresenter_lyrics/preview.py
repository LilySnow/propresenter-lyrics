#!/usr/bin/env python3
"""
preview.py  --  HTML preview of the slides, from the same layout as the .pro.

Uses slide_layout.layout_song(), the same step make_pro.py uses to write the
.pro file, so slide breaks, text, sizes and positions match. The page is drawn
by the browser, so fonts and line spacing are close but not pixel-exact.
No ProPresenter code is involved: the HTML is a self-contained page that works
offline in any browser.

USAGE
    pp-preview song.txt                    # writes song.html next to it
    pp-preview song.txt -o preview.html --config config.yaml

From Python:
    from propresenter_lyrics import slide_layout, preview
    song = slide_layout.layout_song(text, slide_layout.load_config())
    html = preview.render_html(song)
"""

import html as _html
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import slide_layout

_WEIGHTS = (("ultralight", 200), ("thin", 200), ("light", 300), ("semibold", 600),
            ("demibold", 600), ("medium", 500), ("black", 900), ("heavy", 800),
            ("bold", 700), ("w6", 600), ("w3", 400))
_SERIF = ("songti", "georgia", "times", "optima")


def _css_font(ps_name, family, cjk):
    """CSS for a font given by PostScript name + family (weight from the name)."""
    style = ps_name.lower().split("-")[-1]
    weight = next((w for key, w in _WEIGHTS if key in style), 400)
    fallback = ("'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC'"
                if cjk else "'Helvetica Neue',Helvetica,Arial")
    generic = "serif" if any(x in family.lower() for x in _SERIF) else "sans-serif"
    family = re.sub(r"[^\w .\-]", "", family)   # a font name needs nothing else
    return f"font-family:'{family}',{fallback},{generic};font-weight:{weight};"


def _num(v, default=0.0):
    """Config values go into CSS: only ever let numbers through."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rgb(c, default=(255, 255, 255)):
    try:
        return tuple(max(0, min(255, int(round(float(x))))) for x in list(c)[:3])
    except (TypeError, ValueError):
        return default


def _text_css(size, color, stroke):
    size = _num(size, 40)
    r, g, b = _rgb(color)
    css = f"font-size:{size:.1f}px;color:rgb({r},{g},{b});"
    w = _num(stroke.get("width", 0))
    if w:   # ProPresenter's outline width is a % of the font size
        sr, sg, sb = _rgb(stroke.get("color", [0, 0, 0]), (0, 0, 0))
        css += (f"-webkit-text-stroke:{size * abs(w) / 100:.2f}px rgb({sr},{sg},{sb});"
                "paint-order:stroke fill;")
    return css


def _row_div(text, ps_name, family, cjk, size, color, stroke):
    return (f'<div class="row" style="{_css_font(ps_name, family, cjk)}'
            f'{_text_css(size, color, stroke)}">{_html.escape(text)}</div>')


def _slide_div(sl, song):
    color, stroke = song["text_color"], song["stroke"]
    parts = []
    if sl["box"]:
        x, y, w, h = (_num(v) for v in sl["box"])
        just = {"top": "flex-start", "bottom": "flex-end"}.get(sl["valign"], "center")
        rows = "".join(_row_div(r["text"], r["font"], r["family"], r["cjk"], r["size"],
                                color, stroke) for r in sl["rows"])
        parts.append(f'<div class="box lyr" style="left:{x}px;top:{y}px;width:{w}px;'
                     f'height:{h}px;justify-content:{just}">{rows}</div>')
    t = sl["title"]
    if t:
        x, y, w, h = (_num(v) for v in t["box"])
        align = t["align"] if t["align"] in ("left", "center", "right") else "center"
        row = _row_div(t["text"], t["font"], t["family"], slide_layout.has_cjk(t["text"]),
                       t["size"], color, stroke)
        parts.append(f'<div class="box" style="left:{x}px;top:{y}px;width:{w}px;'
                     f'height:{h}px;justify-content:flex-end;text-align:{align}">'
                     f'{row}</div>')
    return f'<div class="slide">{"".join(parts)}</div>'


def slide_count(song):
    return sum(len(sec["slides"]) for sec in song["sections"])


def render_html(song, *, page_title=None, min_tile_px=260, standalone=True):
    """A self-contained HTML page with one thumbnail per slide.

    Each thumbnail shows the section name in its colour and the slide number;
    a red frame marks slides whose text is taller than its text box.
    standalone=False drops the heading and page padding (for embedding)."""
    min_tile_px = int(_num(min_tile_px, 260))
    slide_w, slide_h = (_num(v, d) for v, d in zip(song["slide_size"], (1920, 1080)))
    tiles, i = [], 0
    for sec in song["sections"]:
        r, g, b = _rgb([_num(c) * 255 for c in sec["color"]], (102, 102, 102))
        for sl in sec["slides"]:
            i += 1
            tiles.append(
                f'<div class="tile"><div class="label"><span class="chip" '
                f'style="background:rgb({r},{g},{b})">{_html.escape(sec["name"])}</span>'
                f'<span class="num">{i}</span><span class="warn">⚠ text too tall</span></div>'
                f'<div class="stage">{_slide_div(sl, song)}</div></div>')
    title = _html.escape(page_title or song["title"] or "Slides")
    heading = (f'<h1>{title}</h1><p class="sub">{i} slides · preview — fonts and line '
               f'spacing can differ slightly in ProPresenter</p>' if standalone else "")
    pad = "24px" if standalone else "0"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
  body{{margin:0;padding:{pad};font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;background:#fff;}}
  h1{{font-size:22px;margin:0 0 4px;}} .sub{{margin:0 0 16px;color:#666;font-size:13px;}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax({min_tile_px}px,1fr));gap:12px;}}
  .label{{display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px;color:#666;}}
  .chip{{color:#fff;border-radius:4px;padding:1px 7px;font-weight:600;}}
  .warn{{display:none;color:#c62828;font-weight:600;margin-left:auto;}}
  .tile.over .warn{{display:inline;}} .tile.over .stage{{outline:3px solid #c62828;}}
  .stage{{position:relative;width:100%;aspect-ratio:{slide_w}/{slide_h};overflow:hidden;
          background:#000;border-radius:4px;}}
  .slide{{position:absolute;left:0;top:0;width:{slide_w}px;height:{slide_h}px;
          transform-origin:top left;}}
  .box{{position:absolute;display:flex;flex-direction:column;text-align:center;}}
  .row{{white-space:pre-wrap;line-height:normal;}}
</style></head><body>{heading}<div class="grid">{"".join(tiles)}</div><script>
  function fit(){{
    document.querySelectorAll('.stage').forEach(function(st){{
      st.firstChild.style.transform='scale('+(st.clientWidth/{slide_w})+')';}});
    document.querySelectorAll('.tile').forEach(function(t){{
      var b=t.querySelector('.lyr'); if(!b) return;
      var h=0; b.querySelectorAll('.row').forEach(function(r){{h+=r.offsetHeight;}});
      t.classList.toggle('over', h > b.clientHeight + 1);}});
  }}
  window.addEventListener('resize',fit); fit();
  if(document.fonts) document.fonts.ready.then(fit);
</script></body></html>"""


def main():
    import argparse
    ap = argparse.ArgumentParser(description="HTML preview of the slides pp-make would make")
    ap.add_argument("textfile", help="lyrics file, or '-' to read stdin")
    ap.add_argument("-o", "--out", default=None,
                    help="output .html (default: next to the lyrics file)")
    ap.add_argument("--title", default=None, help="song title (overrides [Title])")
    ap.add_argument("--config", default=None, help="config file (YAML or JSON)")
    args = ap.parse_args()

    if args.textfile == "-":
        raw = sys.stdin.read()
        out = args.out or "preview.html"
    else:
        path = os.path.expanduser(args.textfile)
        raw = open(path, encoding="utf-8").read()
        out = args.out or os.path.splitext(path)[0] + ".html"
    raw = raw.lstrip("﻿")
    song = slide_layout.layout_song(raw, slide_layout.load_config(args.config),
                                    footer_title=args.title)
    for n in song["notes"]:
        sys.stderr.write("note: %s\n" % n)
    out = os.path.expanduser(out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_html(song))
    print("Wrote %s : %d slides" % (out, slide_count(song)))


if __name__ == "__main__":
    main()
