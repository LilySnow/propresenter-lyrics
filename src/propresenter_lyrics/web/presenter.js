/* presenter.js -- control window for showing lyrics without ProPresenter.
 *
 * This page is the operator's control window: a grid of every slide (click to
 * show it), black / clear-text, a background picture or video, and live
 * editing of a slide's text. "Open projector" opens a second window that you
 * drag to the projector screen and make fullscreen; it shows only the slide.
 * Slides are drawn by slides.js, the same code as the preview. Everything
 * works offline from a single file.
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var DATA_START = '<script id="pp-data" type="application/json">';
  var originalHTML = null;  // the page as loaded, taken in start() (whole page parsed)

  var data = JSON.parse($("pp-data").textContent);
  var songs = data.songs;
  var flat = [];            // every slide in show order: {song, i}
  songs.forEach(function (deck, s) {
    deck.slides.forEach(function (_, i) { flat.push({song: s, i: i}); });
  });

  var cur = -1, black = false, clear = false, edited = false, proj = null;
  var bg = {file: null, url: null, dim: 0.35};

  function slideAt(k) { var f = flat[k]; return songs[f.song].slides[f.i]; }
  function deckAt(k) { return songs[flat[k].song]; }

  /* ---------- the grid ---------- */
  var tiles = [];
  function buildGrid() {
    var root = $("songs"); root.textContent = ""; tiles = [];
    var nav = $("songnav"); nav.textContent = "";
    songs.forEach(function (deck, s) {
      var sec = document.createElement("section"); sec.className = "song";
      sec.id = "song-" + s;
      var h = document.createElement("h2");
      h.textContent = deck.title || ("Song " + (s + 1));
      if (deck.order) {
        var o = document.createElement("span"); o.className = "order";
        o.textContent = "order: " + deck.order.join(" "); h.appendChild(o);
      }
      var grid = document.createElement("div"); grid.className = "grid";
      sec.append(h, grid); root.appendChild(sec);
      if (songs.length > 1) {
        var b = document.createElement("button");
        b.textContent = (s + 1) + ". " + (deck.title || "Song " + (s + 1));
        b.onclick = function () { sec.scrollIntoView({behavior: "smooth"}); };
        nav.appendChild(b);
      }
    });
    flat.forEach(function (f, k) {
      var tile = document.createElement("div"); tile.className = "tile";
      tile.onclick = function () { go(k); };
      var label = document.createElement("div"); label.className = "label";
      var chip = document.createElement("span"); chip.className = "chip";
      var n = document.createElement("span"); n.className = "num";
      var warn = document.createElement("span"); warn.className = "warn";
      warn.textContent = "⚠ too tall";
      var ed = document.createElement("span"); ed.className = "edited"; ed.textContent = "edited";
      var pen = document.createElement("button"); pen.className = "pen"; pen.title = "Edit text";
      pen.textContent = "✎";
      pen.onclick = function (e) { e.stopPropagation(); openEditor(k); };
      label.append(chip, n, warn, ed, pen);
      var stage = document.createElement("div"); stage.className = "pp-stage";
      tile.append(label, stage);
      $("song-" + f.song).querySelector(".grid").appendChild(tile);
      tiles.push(tile);
      drawTile(k);
    });
  }

  function drawTile(k) {
    var t = tiles[k], sl = slideAt(k), deck = deckAt(k);
    var chip = t.querySelector(".chip");
    chip.textContent = sl.section;
    chip.style.background = "rgb(" + sl.color.join(",") + ")";
    t.querySelector(".num").textContent = flat[k].i + 1;
    t.classList.toggle("is-edited", !!sl.edited);
    var stage = t.querySelector(".pp-stage");
    stage.style.aspectRatio = deck.slide_size[0] + "/" + deck.slide_size[1];
    stage.textContent = "";
    stage.appendChild(PPSlides.slideElement(deck, sl));
    PPSlides.fitWidth(stage, deck);
    t.classList.toggle("over", PPSlides.overflows(stage.firstElementChild));
  }

  function fitAll() { tiles.forEach(function (_, k) { drawTile(k); }); fitProjector(); }

  function highlight() {
    tiles.forEach(function (t, k) {
      t.classList.toggle("live", k === cur);
      t.classList.toggle("next", k === cur + 1);
    });
    var st = $("status");
    if (cur < 0) st.textContent = "Nothing shown yet — click a slide.";
    else {
      var d = deckAt(cur), sl = slideAt(cur);
      st.textContent = "Showing: " + (d.title ? d.title + " – " : "") + sl.section +
        " (" + (cur + 1) + "/" + flat.length + ")" +
        (black ? " · BLACK" : "") + (clear ? " · text cleared" : "");
    }
    $("btn-black").classList.toggle("on", black);
    $("btn-clear").classList.toggle("on", clear);
  }

  function go(k) {
    if (k < 0 || k >= flat.length) return;
    cur = k;
    clear = false;
    highlight(); showOnProjector();
    tiles[k].scrollIntoView({block: "nearest", behavior: "smooth"});
  }

  /* ---------- the projector window ---------- */
  var PROJECTOR_HTML =
    '<!doctype html><html><head><meta charset="utf-8"><title>Projector</title><style>' +
    'html,body{margin:0;height:100%;background:#000;overflow:hidden;cursor:none;}' +
    '#bg,#dim,#stage,#black{position:fixed;inset:0;}' +
    '#bg img,#bg video{width:100%;height:100%;object-fit:cover;}' +
    '#dim{background:#000;pointer-events:none;}' +
    '#stage.pp-stage{background:transparent;}' +
    '#black{background:#000;display:none;}' +
    '#hint{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);color:#aaa;' +
    'font:15px -apple-system,Helvetica,Arial,sans-serif;background:rgba(0,0,0,.6);' +
    'padding:8px 14px;border-radius:8px;transition:opacity 1s;}' +
    '</style></head><body><div id="bg"></div><div id="dim"></div>' +
    '<div id="stage" class="pp-stage"></div><div id="black"></div>' +
    '<div id="hint">Drag this window to the projector, then double-click (or press F) ' +
    'for fullscreen. Arrow keys work here too.</div></body></html>';

  function projOpen() { return proj && !proj.closed; }

  function openProjector() {
    var w = window.open("", "pp_projector", "popup=yes,width=960,height=540");
    if (!w) {
      alert("The projector window was blocked. Allow pop-ups for this page, then try again.");
      return;
    }
    proj = w;
    var d = w.document;
    d.open(); d.write(PROJECTOR_HTML); d.close();
    PPSlides.injectCSS(d);
    d.addEventListener("keydown", onKey);                       // clickers send keys here
    d.addEventListener("dblclick", function () { fullscreen(w); });
    w.addEventListener("resize", fitProjector);
    setTimeout(function () { var h = d.getElementById("hint"); if (h) h.style.opacity = 0; }, 6000);
    applyBackground(); showOnProjector(); updateProjButton();
    w.focus();
  }

  function fullscreen(w) {
    var el = w.document.documentElement;
    if (!w.document.fullscreenElement && el.requestFullscreen) el.requestFullscreen();
  }

  function updateProjButton() {
    $("btn-proj").textContent = projOpen() ? "▣ Projector open" : "▶ Open projector";
    $("btn-proj").classList.toggle("on", projOpen());
  }
  setInterval(updateProjButton, 1500);

  function showOnProjector() {
    if (!projOpen()) return;
    var d = proj.document, stage = d.getElementById("stage");
    d.getElementById("black").style.display = black ? "block" : "none";
    stage.textContent = "";
    if (cur >= 0 && !clear) {
      stage.appendChild(PPSlides.slideElement(deckAt(cur), slideAt(cur), d));
      PPSlides.fitContain(stage, deckAt(cur));
    }
  }

  function fitProjector() {
    if (!projOpen() || cur < 0) return;
    var stage = proj.document.getElementById("stage");
    if (stage.firstElementChild) PPSlides.fitContain(stage, deckAt(cur));
  }

  /* ---------- black / clear ---------- */
  function toggleBlack() { black = !black; highlight(); showOnProjector(); }
  function toggleClear() { clear = !clear; highlight(); showOnProjector(); }

  /* ---------- background picture / video ---------- */
  function applyBackground() {
    if (!projOpen()) return;
    var d = proj.document, box = d.getElementById("bg");
    box.textContent = "";
    if (bg.url) { try { proj.URL.revokeObjectURL(bg.url); } catch (e) {} bg.url = null; }
    d.getElementById("dim").style.opacity = bg.file ? bg.dim : 0;
    if (!bg.file) return;
    bg.url = proj.URL.createObjectURL(bg.file);
    var isVideo = /^video\//.test(bg.file.type);
    var el = d.createElement(isVideo ? "video" : "img");
    el.src = bg.url;
    if (isVideo) {
      el.muted = true; el.loop = true; el.autoplay = true; el.playsInline = true;
      el.play && el.play().catch(function () {});
    }
    box.appendChild(el);
  }

  function setBackground(file) {
    bg.file = file || null;
    $("bg-name").textContent = file ? file.name : "none";
    $("btn-bg-off").disabled = !file;
    applyBackground();
  }

  /* ---------- live editing ---------- */
  var editing = -1;
  function openEditor(k) {
    editing = k;
    var sl = slideAt(k), form = $("ed-fields");
    form.textContent = "";
    $("ed-title").textContent = "Edit: " + sl.section + " (slide " + (flat[k].i + 1) + ")";
    sl.rows.forEach(function (r, idx) {
      if (r.role === "pinyin" || r.role === "spacer") return;
      var wrap = document.createElement("label"); wrap.className = "ed-row";
      var cap = document.createElement("span");
      cap.textContent = r.role === "translation" ? "Translation" : "Lyric";
      var inp = document.createElement("input"); inp.type = "text"; inp.value = r.text;
      inp.dataset.idx = idx;
      wrap.append(cap, inp);
      var prev = sl.rows[idx - 1];
      if (r.cjk && prev && prev.role === "pinyin") {
        var py = document.createElement("small"); py.className = "ed-py";
        var upd = function () {
          var p = PPSlides.pinyinLine(inp.value);
          py.textContent = "Pinyin: " + (p === null && !window.pinyinPro ? "(not available)" : (p || "—"));
        };
        inp.addEventListener("input", upd); upd();
        wrap.appendChild(py);
      }
      form.appendChild(wrap);
    });
    $("editor").hidden = false;
    var first = form.querySelector("input"); if (first) first.focus();
  }

  function closeEditor() { $("editor").hidden = true; editing = -1; }

  function saveEditor() {
    if (editing < 0) return;
    var key = slideAt(editing).key, song = flat[editing].song;
    var inputs = $("ed-fields").querySelectorAll("input");
    // apply to this slide and every repeat of it ([Order]) in the same song
    flat.forEach(function (f, k) {
      if (f.song !== song || slideAt(k).key !== key) return;
      var sl = slideAt(k), changed = false;
      inputs.forEach(function (inp) {
        var idx = +inp.dataset.idx, row = sl.rows[idx];
        if (row.text === inp.value) return;
        row.text = inp.value; changed = true;
        var prev = sl.rows[idx - 1];
        if (row.cjk && prev && prev.role === "pinyin") {
          var p = PPSlides.pinyinLine(inp.value);
          if (p !== null || window.pinyinPro) prev.text = p || "";
        }
      });
      if (changed) { sl.edited = true; edited = true; drawTile(k); }
    });
    closeEditor();
    if (cur >= 0 && slideAt(cur).key === key && flat[cur].song === song) showOnProjector();
    $("btn-save").classList.toggle("attention", edited);
  }

  /* ---------- save a copy with the edits ---------- */
  function saveCopy() {
    var start = originalHTML.indexOf(DATA_START);
    var end = originalHTML.indexOf("<\/script>", start);   // written escaped: this file sits in a <script>
    if (start < 0 || end < 0) { alert("Could not save a copy."); return; }
    var json = JSON.stringify(data).replace(/<\//g, "<\\/")
      .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    var html = originalHTML.slice(0, start + DATA_START.length) + json + originalHTML.slice(end);
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([html], {type: "text/html"}));
    a.download = (document.title || "presenter").replace(/[\\/:*?"<>|]+/g, "_") + " (edited).html";
    document.body.appendChild(a); a.click(); a.remove();
    edited = false; $("btn-save").classList.remove("attention");
  }

  window.addEventListener("beforeunload", function (e) {
    if (edited) { e.preventDefault(); e.returnValue = ""; }
  });

  /* ---------- keys (in this window and in the projector window) ---------- */
  function onKey(e) {
    var tag = (e.target && e.target.tagName) || "";
    if (!$("editor").hidden) {
      if (e.key === "Escape") closeEditor();
      if (e.key === "Enter" && tag === "INPUT") { e.preventDefault(); saveEditor(); }
      return;
    }
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    var k = e.key;
    if (k === "ArrowRight" || k === "ArrowDown" || k === "PageDown" || k === " ") {
      e.preventDefault(); go(cur < 0 ? 0 : Math.min(cur + 1, flat.length - 1));
    } else if (k === "ArrowLeft" || k === "ArrowUp" || k === "PageUp") {
      e.preventDefault(); go(Math.max(cur - 1, 0));
    } else if (k === "b" || k === "B" || k === ".") {
      toggleBlack();
    } else if (k === "c" || k === "C") {
      toggleClear();
    } else if ((k === "f" || k === "F") && projOpen() && e.view === proj) {
      fullscreen(proj);
    }
  }

  /* ---------- start ---------- */
  function start() {
    // copy of the page before anything is drawn: "Save a copy" swaps in the edited data
    originalHTML = "<!doctype html>\n" + document.documentElement.outerHTML;
    document.addEventListener("keydown", onKey);
    $("btn-proj").onclick = openProjector;
    $("btn-black").onclick = toggleBlack;
    $("btn-clear").onclick = toggleClear;
    $("btn-save").onclick = saveCopy;
    $("bg-file").onchange = function () { setBackground(this.files[0]); this.value = ""; };
    $("btn-bg-off").onclick = function () { setBackground(null); };
    $("bg-dim").oninput = function () { bg.dim = this.value / 100; applyBackground(); };
    $("ed-save").onclick = saveEditor;
    $("ed-cancel").onclick = closeEditor;
    $("editor").addEventListener("click", function (e) { if (e.target === this) closeEditor(); });
    if (!window.pinyinPro) $("pinyin-note").hidden = false;
    buildGrid(); highlight(); updateProjButton();
    window.addEventListener("resize", fitAll);
    if (document.fonts) document.fonts.ready.then(fitAll);
  }

  window.PPPresenter = {start: start,
                        // for tests and scripting
                        go: go, state: function () {
                          return {cur: cur, black: black, clear: clear, edited: edited,
                                  projector: projOpen(), slides: flat.length};
                        }};
})();
