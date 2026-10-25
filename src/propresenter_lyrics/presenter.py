#!/usr/bin/env python3
"""
presenter.py  --  show lyrics from a single HTML file, without ProPresenter.

Builds one self-contained, offline HTML file for one or more songs (a whole
service). Open it in a browser; it is the operator's control window:

  - a grid of every slide (in [Order] if given); click one to show it,
    or use the arrow keys / PageDown / space (also from a presentation clicker)
  - "Open projector": a second window to drag onto the projector screen;
    double-click it (or press F there) for fullscreen
  - B = black screen, C = clear text (background stays)
  - a background picture or video, chosen on the day, with a darken slider
  - live editing: the pencil on a slide edits its text; pinyin is redone for
    edited Chinese lines; "Save a copy" downloads the file with the edits

Slides are laid out by slide_layout.py and drawn by web/slides.js, exactly as
in the preview and the same as the .pro file.

USAGE
    pp-present song1.txt song2.txt song3.txt -o sunday.html [--config config.yaml]
"""

import html as _html
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import slide_layout
from preview import deck, json_for_script, web_file


_CSS = """
  :root{--bar:#1f2430;--fg:#e7e9ee;--muted:#9aa2b2;}
  body{margin:0;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;background:#f4f5f7;color:#222;}
  header{position:sticky;top:0;z-index:5;background:var(--bar);color:var(--fg);padding:10px 16px;
         display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;box-shadow:0 2px 8px rgba(0,0,0,.25);}
  header h1{font-size:16px;margin:0 8px 0 0;}
  header button,header label.btn{font:inherit;font-size:14px;border:0;border-radius:7px;padding:7px 12px;
         cursor:pointer;background:#3a4152;color:var(--fg);}
  header button.on{background:#2e7d32;} #btn-black.on{background:#000;outline:2px solid #fff;}
  #btn-clear.on{background:#8d6e00;} #btn-save.attention{background:#c62828;}
  header button:disabled{opacity:.4;cursor:default;}
  .group{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--muted);}
  #bg-name{color:var(--fg);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  #status{flex-basis:100%;font-size:13px;color:var(--muted);}
  #songnav{display:flex;gap:6px;flex-wrap:wrap;} #songnav button{font-size:12px;padding:4px 9px;}
  main{padding:16px;}
  .song h2{font-size:18px;margin:8px 0 10px;} .song h2 .order{font-size:13px;color:#666;
          font-weight:400;margin-left:10px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:24px;}
  .tile{cursor:pointer;border-radius:6px;padding:4px;border:3px solid transparent;}
  .tile:hover{border-color:#90a4ae;} .tile.live{border-color:#2e7d32;background:#e8f5e9;}
  .tile.next{border-color:#64b5f6;border-style:dashed;}
  .label{display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px;color:#666;}
  .chip{color:#fff;border-radius:4px;padding:1px 7px;font-weight:600;}
  .warn,.edited{display:none;font-weight:600;} .warn{color:#c62828;} .edited{color:#6a1b9a;}
  .tile.over .warn,.tile.is-edited .edited{display:inline;}
  .pen{margin-left:auto;border:0;background:#eceff1;border-radius:5px;cursor:pointer;font-size:13px;padding:1px 7px;}
  .tile .pp-stage{width:100%;border-radius:4px;}
  .tile.over .pp-stage{outline:3px solid #c62828;}
  #editor{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10;display:flex;
          align-items:center;justify-content:center;}
  #editor[hidden]{display:none;}
  .ed-box{background:#fff;border-radius:10px;padding:18px;width:min(640px,92vw);max-height:85vh;overflow:auto;}
  .ed-box h3{margin:0 0 12px;font-size:16px;}
  .ed-row{display:block;margin-bottom:12px;font-size:12px;color:#666;}
  .ed-row input{display:block;width:100%;box-sizing:border-box;font-size:17px;padding:7px 9px;margin-top:3px;
                border:1px solid #bbb;border-radius:6px;}
  .ed-py{display:block;color:#888;margin-top:3px;}
  .ed-actions{display:flex;gap:8px;justify-content:flex-end;}
  .ed-actions button{font:inherit;padding:7px 14px;border-radius:7px;border:0;cursor:pointer;}
  #ed-save{background:#2e7d32;color:#fff;}
  #pinyin-note{color:#ffcc80;font-size:12px;}
"""

_BODY = """
<header>
  <h1>%(title)s</h1>
  <button id="btn-proj">&#9654; Open projector</button>
  <button id="btn-black" title="Black screen (key B)">&#9632; Black (B)</button>
  <button id="btn-clear" title="Hide the text, keep the background (key C)">Clear text (C)</button>
  <span class="group">Background:
    <label class="btn">Choose&hellip;<input id="bg-file" type="file" accept="image/*,video/*" hidden></label>
    <span id="bg-name">none</span>
    <button id="btn-bg-off" disabled>&#10005;</button>
    darken <input id="bg-dim" type="range" min="0" max="90" value="35">
  </span>
  <button id="btn-save" title="Download this file with your edits">Save a copy</button>
  <span id="pinyin-note" hidden>(pinyin for edited lines not available)</span>
  <nav id="songnav"></nav>
  <div id="status"></div>
</header>
<main id="songs"></main>
<div id="editor" hidden><div class="ed-box">
  <h3 id="ed-title">Edit</h3>
  <div id="ed-fields"></div>
  <p style="font-size:12px;color:#888;margin:0 0 12px">Changes show on the projector right away
  and apply to every repeat of this slide. They stay in this file only: use
  "Save a copy" to keep them, and update your lyrics file for next time.</p>
  <div class="ed-actions"><button id="ed-cancel">Cancel</button><button id="ed-save">Save (Enter)</button></div>
</div></div>
"""


def _script(name):
    js = web_file(name)
    if "</script" in js.lower():          # would end the <script> tag early
        raise ValueError("%s contains '</script' and can't be embedded" % name)
    return "<script>" + js + "</script>"


def render_presenter_html(songs, *, page_title=None):
    """One HTML file presenting `songs` (a list of slide_layout.layout_song
    results), in that order."""
    data = {"songs": [deck(s) for s in songs]}
    if page_title is None:
        titles = [d["title"] for d in data["songs"] if d["title"]]
        page_title = titles[0] if len(songs) == 1 and titles else (
            "Service (%d songs)" % len(songs) if len(songs) > 1 else "Slides")
    title = _html.escape(page_title)
    return ("<!doctype html><html><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>" + title + "</title><style>" + _CSS + "</style>\n"
            + _script("pinyin-pro.js") + "\n" + _script("slides.js") + "\n"
            "</head><body>" + (_BODY % {"title": title}) + "\n"
            "<script id=\"pp-data\" type=\"application/json\">" + json_for_script(data)
            + "</script>\n" + _script("presenter.js") + "\n"
            "<script>PPPresenter.start();</script>\n</body></html>")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Make one HTML file to present songs without ProPresenter")
    ap.add_argument("textfiles", nargs="+", help="lyrics files, in service order")
    ap.add_argument("-o", "--out", default=None,
                    help="output .html (default: next to the first file, or service.html)")
    ap.add_argument("--config", default=None, help="config file (YAML or JSON)")
    ap.add_argument("--name", default=None, help="title shown at the top of the page")
    args = ap.parse_args()

    cfg = slide_layout.load_config(args.config)
    songs = []
    for f in args.textfiles:
        path = os.path.expanduser(f)
        raw = open(path, encoding="utf-8").read().lstrip("﻿")
        song = slide_layout.layout_song(raw, cfg)
        if not song["title"]:
            song["title"] = os.path.splitext(os.path.basename(path))[0]
        for n in song["notes"]:
            sys.stderr.write("note: %s: %s\n" % (os.path.basename(path), n))
        songs.append(song)
    out = args.out or (os.path.splitext(os.path.expanduser(args.textfiles[0]))[0] + ".html"
                       if len(songs) == 1 else "service.html")
    out = os.path.expanduser(out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_presenter_html(songs, page_title=args.name))
    n = sum(len(deck(s)["slides"]) for s in songs)
    print("Wrote %s : %d song(s), %d slides" % (out, len(songs), n))


if __name__ == "__main__":
    main()
