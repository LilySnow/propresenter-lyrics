#!/usr/bin/env python3
"""
preview.py  --  HTML preview of the slides, from the same layout as the .pro.

Uses slide_layout.layout_song(), the same step make_pro.py uses to write the
.pro file, so slide breaks, text, sizes and positions match. The slides are
drawn in the browser by web/slides.js, which the presenter (presenter.py) uses
too, so preview and presenter look the same. Fonts and line spacing are the
browser's: close to ProPresenter but not pixel-exact. The HTML is a
self-contained page that works offline in any browser.

USAGE
    pp-preview song.txt                    # writes song.html next to it
    pp-preview song.txt -o preview.html --config config.yaml

From Python:
    from propresenter_lyrics import slide_layout, preview
    song = slide_layout.layout_song(text, slide_layout.load_config())
    html = preview.render_html(song)
"""

import html as _html
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import slide_layout

WEB_DIR = os.path.join(_HERE, "web")


def web_file(name):
    """Contents of a file in the package's web/ folder (JS for the pages)."""
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _num(v, default=0.0):
    """Config values become numbers before they reach a page."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rgb255(c, default=(255, 255, 255)):
    try:
        return [max(0, min(255, int(round(float(x))))) for x in list(c)[:3]]
    except (TypeError, ValueError):
        return list(default)


def _row_json(r):
    return {"text": str(r["text"]), "font": str(r["font"]), "family": str(r["family"]),
            "size": _num(r["size"], 40), "cjk": bool(r["cjk"]),
            "role": str(r.get("role", "primary"))}


def deck(song):
    """The song as plain JSON-ready data for web/slides.js: slides in play
    order ([Order] if given), every number really a number."""
    slides = []
    for item in slide_layout.play_slides(song):
        sec, sl = item["section"], item["slide"]
        t = sl["title"]
        slides.append({
            "section": str(sec["name"]),
            "section_index": item["section_index"],
            # same key = same slide shown again via [Order]; edits apply to all
            "key": "%d:%d" % (item["section_index"], item["slide_index"]),
            "color": _rgb255([_num(c) * 255 for c in sec["color"]], (102, 102, 102)),
            "rows": [_row_json(r) for r in sl["rows"]],
            "box": [_num(v) for v in sl["box"]] if sl["box"] else None,
            "valign": sl["valign"] if sl["valign"] in ("top", "middle", "bottom") else "middle",
            "title": None if not t else {
                "text": str(t["text"]), "font": str(t["font"]), "family": str(t["family"]),
                "size": _num(t["size"], 40), "box": [_num(v) for v in t["box"]],
                "align": t["align"] if t["align"] in ("left", "center", "right") else "center"},
        })
    stroke = song["stroke"] or {}
    order = None
    if song.get("order"):
        order = [slide_layout.section_code(song["sections"][i]["name"]) for i in song["order"]]
    return {
        "title": str(song["title"] or ""),
        "slide_size": [_num(song["slide_size"][0], 1920), _num(song["slide_size"][1], 1080)],
        "text_color": _rgb255(song["text_color"]),
        "stroke": {"width": _num(stroke.get("width", 0)),
                   "color": _rgb255(stroke.get("color", [0, 0, 0]), (0, 0, 0))},
        "order": order,
        "slides": slides,
    }


def json_for_script(data):
    """JSON safe to place inside <script type="application/json">."""
    return (json.dumps(data, ensure_ascii=False)
            .replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def slide_count(song):
    """Slides as shown, following [Order] (repeats counted)."""
    return sum(1 for _ in slide_layout.play_slides(song))


_PAGE_CSS = """
  body{margin:0;padding:%(pad)s;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;background:#fff;}
  h1{font-size:22px;margin:0 0 4px;} .sub{margin:0 0 16px;color:#666;font-size:13px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(%(tile)dpx,1fr));gap:12px;}
  .label{display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px;color:#666;}
  .chip{color:#fff;border-radius:4px;padding:1px 7px;font-weight:600;}
  .warn{display:none;color:#c62828;font-weight:600;margin-left:auto;}
  .tile.over .warn{display:inline;} .tile.over .pp-stage{outline:3px solid #c62828;}
  .tile .pp-stage{width:100%%;aspect-ratio:%(w)s/%(h)s;border-radius:4px;}
"""

_PAGE_JS = """
(function () {
  var deck = JSON.parse(document.getElementById("pp-data").textContent);
  var grid = document.getElementById("grid");
  deck.slides.forEach(function (sl, i) {
    var tile = document.createElement("div"); tile.className = "tile";
    var label = document.createElement("div"); label.className = "label";
    var chip = document.createElement("span"); chip.className = "chip";
    chip.textContent = sl.section;
    chip.style.background = "rgb(" + sl.color.join(",") + ")";
    var n = document.createElement("span"); n.className = "num"; n.textContent = i + 1;
    var w = document.createElement("span"); w.className = "warn"; w.textContent = "\\u26a0 text too tall";
    label.append(chip, n, w);
    var stage = document.createElement("div"); stage.className = "pp-stage";
    stage.appendChild(PPSlides.slideElement(deck, sl));
    tile.append(label, stage); grid.appendChild(tile);
  });
  function fit() {
    grid.querySelectorAll(".tile").forEach(function (t) {
      var st = t.querySelector(".pp-stage");
      PPSlides.fitWidth(st, deck);
      t.classList.toggle("over", PPSlides.overflows(st.firstElementChild));
    });
  }
  window.addEventListener("resize", fit); fit();
  if (document.fonts) document.fonts.ready.then(fit);
})();
"""


def render_html(song, *, page_title=None, min_tile_px=260, standalone=True):
    """A self-contained HTML page with one thumbnail per slide.

    Each thumbnail shows the section name in its colour and the slide number;
    a red frame marks slides whose text is taller than its text box.
    standalone=False drops the heading and page padding (for embedding)."""
    d = deck(song)
    title = _html.escape(page_title or d["title"] or "Slides")
    n = len(d["slides"])
    order = (" · order: " + _html.escape(" ".join(d["order"]))) if d["order"] else ""
    heading = (f'<h1>{title}</h1><p class="sub">{n} slides{order} · preview — fonts and '
               f'line spacing can differ slightly in ProPresenter</p>' if standalone else "")
    css = _PAGE_CSS % {"pad": "24px" if standalone else "0",
                       "tile": int(_num(min_tile_px, 260)),
                       "w": d["slide_size"][0], "h": d["slide_size"][1]}
    return (f'<!doctype html><html><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{title}</title><style>{css}</style>\n'
            f'<script>{web_file("slides.js")}</script>\n'
            f'</head><body>{heading}<div class="grid" id="grid"></div>\n'
            f'<script id="pp-data" type="application/json">{json_for_script(d)}</script>\n'
            f'<script>{_PAGE_JS}</script></body></html>')


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
    raw = raw.lstrip("\ufeff")
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
