/* slides.js -- draws slides from the layout made by slide_layout.py.
 *
 * Shared by the preview (preview.py) and the presenter (presenter.py), so both
 * draw slides exactly the same way. Input is a "deck" (JSON):
 *   {slide_size:[w,h], text_color:[r,g,b], stroke:{width, color:[r,g,b]},
 *    slides:[{section, color:[r,g,b], rows:[{text,font,family,size,cjk,role}],
 *             box:[x,y,w,h]|null, valign, title:{text,font,family,size,box,align}|null}]}
 * All text is inserted as text (never as HTML), so lyrics can't inject markup.
 */
(function (root) {
  "use strict";

  var WEIGHTS = [["ultralight", 200], ["thin", 200], ["light", 300], ["semibold", 600],
                 ["demibold", 600], ["medium", 500], ["black", 900], ["heavy", 800],
                 ["bold", 700], ["w6", 600], ["w3", 400]];
  var SERIF = ["songti", "georgia", "times", "optima"];

  function num(v, d) { v = Number(v); return isFinite(v) ? v : (d || 0); }
  function rgb(c, d) {
    if (!c || c.length < 3) return d;
    return "rgb(" + [0, 1, 2].map(function (i) {
      return Math.max(0, Math.min(255, Math.round(num(c[i]))));
    }).join(",") + ")";
  }
  function pick(v, allowed, d) { return allowed.indexOf(v) >= 0 ? v : d; }

  // CSS font for a PostScript name + family (weight comes from the name)
  function fontCss(el, psName, family, cjk) {
    var style = String(psName || "").toLowerCase().split("-").pop();
    var weight = 400;
    for (var i = 0; i < WEIGHTS.length; i++)
      if (style.indexOf(WEIGHTS[i][0]) >= 0) { weight = WEIGHTS[i][1]; break; }
    var fam = String(family || "").replace(/[^\w .\-]/g, "");   // a font name needs nothing else
    var fallback = cjk ? "'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC'"
                       : "'Helvetica Neue',Helvetica,Arial";
    var generic = SERIF.some(function (s) { return fam.toLowerCase().indexOf(s) >= 0; })
                  ? "serif" : "sans-serif";
    el.style.fontFamily = "'" + fam + "'," + fallback + "," + generic;
    el.style.fontWeight = weight;
  }

  // size, colour and ProPresenter-style outline (width = % of the font size)
  function textCss(el, size, color, stroke) {
    size = num(size, 40);
    el.style.fontSize = size.toFixed(1) + "px";
    el.style.color = rgb(color, "rgb(255,255,255)");
    var w = Math.abs(num(stroke && stroke.width));
    if (w) {
      el.style.webkitTextStroke = (size * w / 100).toFixed(2) + "px " +
        rgb(stroke.color, "rgb(0,0,0)");
      el.style.paintOrder = "stroke fill";
    }
  }

  function rowEl(doc, text, psName, family, cjk, size, deck) {
    var d = doc.createElement("div");
    d.className = "pp-row";
    d.textContent = text;
    fontCss(d, psName, family, cjk);
    textCss(d, size, deck.text_color, deck.stroke);
    return d;
  }

  function boxEl(doc, box, justify, align) {
    var b = doc.createElement("div");
    b.className = "pp-box";
    b.style.left = num(box[0]) + "px"; b.style.top = num(box[1]) + "px";
    b.style.width = num(box[2]) + "px"; b.style.height = num(box[3]) + "px";
    b.style.justifyContent = justify;
    b.style.textAlign = align;
    return b;
  }

  var CJK_RE = /[぀-ヿ㐀-䶿一-鿿豈-﫿가-힣]/;

  // One slide as a full-size (e.g. 1920x1080) element; scale it with fit().
  function slideElement(deck, slide, doc) {
    doc = doc || document;
    var size = deck.slide_size || [1920, 1080];
    var s = doc.createElement("div");
    s.className = "pp-slide";
    s.style.width = num(size[0], 1920) + "px";
    s.style.height = num(size[1], 1080) + "px";
    if (slide.box) {
      var just = {top: "flex-start", bottom: "flex-end"}[slide.valign] || "center";
      var b = boxEl(doc, slide.box, just, "center");
      b.classList.add("pp-lyrics");
      (slide.rows || []).forEach(function (r) {
        b.appendChild(rowEl(doc, r.text, r.font, r.family, r.cjk, r.size, deck));
      });
      s.appendChild(b);
    }
    var t = slide.title;
    if (t) {
      var tb = boxEl(doc, t.box, "flex-end", pick(t.align, ["left", "center", "right"], "center"));
      tb.appendChild(rowEl(doc, t.text, t.font, t.family, CJK_RE.test(t.text), t.size, deck));
      s.appendChild(tb);
    }
    return s;
  }

  // Scale the slide inside `stage` to the stage's width (thumbnails)
  function fitWidth(stage, deck) {
    var el = stage.firstElementChild; if (!el) return;
    el.style.transform = "scale(" + (stage.clientWidth / num(deck.slide_size[0], 1920)) + ")";
  }

  // Scale and centre the slide in a window of any shape (letterboxed, projector)
  function fitContain(stage, deck) {
    var el = stage.firstElementChild; if (!el) return;
    var W = num(deck.slide_size[0], 1920), H = num(deck.slide_size[1], 1080);
    var k = Math.min(stage.clientWidth / W, stage.clientHeight / H);
    el.style.transform = "translate(" + (stage.clientWidth - W * k) / 2 + "px," +
      (stage.clientHeight - H * k) / 2 + "px) scale(" + k + ")";
  }

  // True when the lyric rows are taller than their text box
  function overflows(slideEl) {
    var b = slideEl.querySelector(".pp-lyrics"); if (!b) return false;
    var h = 0;
    b.querySelectorAll(".pp-row").forEach(function (r) { h += r.offsetHeight; });
    return h > b.clientHeight + 1;
  }

  // ALL-CAPS toneless pinyin, like slide_layout.pinyin_line (needs pinyin-pro)
  function pinyinLine(text) {
    var P = root.pinyinPro;
    if (!P) return null;
    var t = String(text).replace(/祢/g, "你").replace(/祂/g, "他");
    try {
      return P.pinyin(t, {toneType: "none", nonZh: "removed", type: "array"})
        .join(" ").toUpperCase().replace(/\s+/g, " ").trim() || null;
    } catch (e) { return null; }
  }
  if (root.pinyinPro && root.pinyinPro.customPinyin)
    root.pinyinPro.customPinyin({"於": "yú"});   // as pypinyin reads it in lyrics

  // CSS every page that shows slides needs
  var CSS =
    ".pp-stage{position:relative;overflow:hidden;background:#000;}" +
    ".pp-slide{position:absolute;left:0;top:0;transform-origin:top left;}" +
    ".pp-box{position:absolute;display:flex;flex-direction:column;}" +
    ".pp-row{white-space:pre-wrap;line-height:normal;}";

  // Add the CSS to a document (this page, or a projector window's page)
  function injectCSS(doc) {
    if (!doc || doc.getElementById("pp-slides-css")) return;
    var st = doc.createElement("style");
    st.id = "pp-slides-css"; st.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(st);
  }
  if (root.document) injectCSS(root.document);

  root.PPSlides = {slideElement: slideElement, fitWidth: fitWidth, fitContain: fitContain,
                   overflows: overflows, pinyinLine: pinyinLine, CSS: CSS,
                   injectCSS: injectCSS};
})(typeof window !== "undefined" ? window : this);
