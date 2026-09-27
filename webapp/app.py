"""
ProPresenter Lyrics -- web interface.

Paste lyrics, optionally let Claude fix reverence pronouns and add translations,
review the result, and download a ProPresenter 7 (.pro) file.

Environment variables (set them as "secrets" on your host):
    ANTHROPIC_API_KEY   your Claude API key (needed only for the Claude step)
    APP_PASSWORD        password users must enter to use the Claude step
                        (leave unset to disable the password -- not recommended)
    DAILY_LIMIT         max Claude runs per day across all users (default 50)
    MAX_CHARS           max lyrics length sent to Claude (default 8000)

Run locally:
    pip install -e . streamlit
    streamlit run webapp/app.py
"""

import contextlib
import copy
import datetime as dt
import hmac
import io
import os
import re
import threading

import streamlit as st
import yaml

from propresenter_lyrics import make_pro, prep_lyrics

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "50"))
MAX_CHARS = int(os.environ.get("MAX_CHARS", "8000"))
HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

EXAMPLE = """[Title]
使我们合一

[Verse 1]
求主留我於十架//在彼有生命水 | Heer, houd mij dicht bij het kruis//Daar stroomt het water
在你的爱里面 | In uw liefde

[Chorus]
我们在你爱中合一

[youtube]
https://youtu.be/xxxx
"""

st.set_page_config(page_title="ProPresenter Lyrics", page_icon="🎵", layout="centered")


# ---------------------------------------------------------------------------
# Shared daily usage counter for the Claude step (all users together).
# Lives in server memory, so it also resets whenever the app restarts.
# ---------------------------------------------------------------------------
@st.cache_resource
def _usage():
    return {"day": None, "count": 0, "lock": threading.Lock()}


def runs_left():
    u = _usage()
    with u["lock"]:
        today = dt.date.today().isoformat()
        if u["day"] != today:
            u["day"], u["count"] = today, 0
        return max(0, DAILY_LIMIT - u["count"])


def take_run():
    """Reserve one Claude run. Returns False if today's limit is reached."""
    u = _usage()
    with u["lock"]:
        today = dt.date.today().isoformat()
        if u["day"] != today:
            u["day"], u["count"] = today, 0
        if u["count"] >= DAILY_LIMIT:
            return False
        u["count"] += 1
        return True


def password_ok(entered):
    if not APP_PASSWORD:
        return True
    return hmac.compare_digest(entered.encode("utf-8"), APP_PASSWORD.encode("utf-8"))


# ---------------------------------------------------------------------------
# State + callbacks
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("lyrics", "")
ss.setdefault("prep_msgs", [])
ss.setdefault("before_prep", None)
ss.setdefault("upload_id", None)


def load_example():
    ss.lyrics = EXAMPLE


def undo_prep():
    if ss.before_prep is not None:
        ss.lyrics = ss.before_prep
        ss.before_prep = None
        ss.prep_msgs = []


def run_prep():
    text = ss.lyrics
    ss.prep_msgs = []
    if not text.strip():
        ss.prep_msgs = [("error", "Paste some lyrics first.")]
        return
    uses_claude = ss.opt_pronouns or ss.opt_translate
    if uses_claude:
        if not HAS_KEY:
            ss.prep_msgs = [("error", "The Claude step is not configured on this server "
                                      "(no API key).")]
            return
        if not password_ok(ss.get("password", "")):
            ss.prep_msgs = [("error", "Wrong password.")]
            return
        if len(text) > MAX_CHARS:
            ss.prep_msgs = [("error", f"Lyrics are too long for the Claude step "
                                      f"({len(text)} characters, max {MAX_CHARS}). "
                                      "Split the song and run it in parts.")]
            return
        if not take_run():
            ss.prep_msgs = [("error", "Today's limit for the Claude step has been reached. "
                                      "Please try again tomorrow.")]
            return
    other = ss.get("opt_other_custom", "").strip() if ss.opt_other == "Other…" else ss.opt_other
    try:
        result, warnings = prep_lyrics.prep_text(
            text,
            other_lang=other or "Dutch",
            do_pronouns=ss.opt_pronouns,
            do_translate=ss.opt_translate,
            tag_fix=True,
            traditional=ss.opt_traditional,
        )
    except Exception as e:  # network / API errors
        ss.prep_msgs = [("error", f"Something went wrong: {e}")]
        return
    ss.before_prep = text
    ss.lyrics = result
    ss.prep_msgs = [("warning", w) for w in warnings] + [
        ("success", "Done. **Please review the text below** — pronouns and "
                    "translations are theology-sensitive. You can edit it directly.")]


# ---------------------------------------------------------------------------
# Sidebar: slide appearance
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Slide appearance")
    cfg_file = st.file_uploader(
        "Load a config file (optional)", type=["yaml", "yml", "json"],
        help="A config.yaml made with `pp-make --init-config`. "
             "The settings below start from it.")
    base = copy.deepcopy(make_pro.DEFAULT_CONFIG)
    cfg_key = "default"
    if cfg_file is not None:
        try:
            raw = cfg_file.getvalue().decode("utf-8")
            loaded = yaml.safe_load(raw) or {}   # YAML also parses JSON
            if not isinstance(loaded, dict):
                raise ValueError("not a mapping")
            base = make_pro._deep_merge(base, loaded)
            cfg_key = f"{cfg_file.name}-{cfg_file.size}"
        except Exception as e:
            st.error(f"Could not read that config file: {e}")

    k = lambda name: f"{name}-{cfg_key}"   # widgets reset when a new file is loaded

    traditional_font = st.checkbox(
        "Use Traditional Chinese font (PingFang TC)",
        value="TC" in base["chinese"]["primary"]["font"], key=k("tc"))

    st.subheader("Chinese lyric lines")
    zh_pinyin = st.number_input("Pinyin size", 10, 400, int(base["chinese"]["pinyin"]["size"]), key=k("zp"))
    zh_primary = st.number_input("Chinese size", 10, 400, int(base["chinese"]["primary"]["size"]), key=k("zc"))
    zh_trans = st.number_input("Translation size", 10, 400, int(base["chinese"]["translation"]["size"]), key=k("zt"))

    st.subheader("Dutch / English lyric lines")
    la_primary = st.number_input("Lyric size", 10, 400, int(base["latin"]["primary"]["size"]), key=k("lp"))
    la_trans = st.number_input("Chinese translation size", 10, 400, int(base["latin"]["translation"]["size"]), key=k("lt"))

    st.subheader("Layout")
    title_size = st.number_input("Song title size", 10, 400, int(base["title"]["size"]), key=k("ts"))
    title_align = st.selectbox("Song title position", ["left", "center", "right"],
                               index=["left", "center", "right"].index(base["title"]["align"]),
                               key=k("ta"))
    valign = st.selectbox("Lyrics position", ["top", "middle", "bottom"],
                          index=["top", "middle", "bottom"].index(base["vertical_align"]),
                          key=k("va"))
    stroke = st.number_input("Text outline width (0 = off)", 0, 50, int(base["stroke"]["width"]), key=k("sw"))
    gap = st.number_input("Gap between lyric and translation", 0, 400, int(base["translation_gap"]), key=k("gap"))

cfg = copy.deepcopy(base)
cfg["chinese"]["pinyin"]["size"] = zh_pinyin
cfg["chinese"]["primary"]["size"] = zh_primary
cfg["chinese"]["translation"]["size"] = zh_trans
cfg["latin"]["primary"]["size"] = la_primary
cfg["latin"]["translation"]["size"] = la_trans
cfg["title"]["size"] = title_size
cfg["title"]["align"] = title_align
cfg["vertical_align"] = valign
cfg["stroke"]["width"] = stroke
cfg["translation_gap"] = gap
zh_font = ("PingFangTC-Regular", "PingFang TC") if traditional_font else ("PingFangSC-Regular", "PingFang SC")
for tier in (cfg["chinese"]["primary"], cfg["latin"]["translation"]):
    if tier["font"].startswith("PingFang"):
        tier["font"], tier["family"] = zh_font


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------
st.title("🎵 ProPresenter Lyrics")
st.write("Turn song lyrics into a ready-to-import **ProPresenter 7** file — with "
         "pinyin, bilingual layout and coloured song sections.")

with st.expander("How to write the lyrics"):
    st.markdown("""
- Start each part with a tag on its own line: `[Title]`, `[Verse 1]`, `[Chorus]`,
  `[Bridge]`, `[Pre-Chorus]`, `[Intro]`, `[Outro]`, `[Tag]` …
- Put a translation after a bar: `在你的爱里面 | In uw liefde`
- `//` inside a line = line break. `//` on its own line = new slide.
  Otherwise each lyric line gets its own slide.
- Chinese lines automatically get **pinyin** on top.
- Other tags such as `[youtube]` or `[ccli]` are ignored.
""")
    st.button("Load an example", on_click=load_example)

# --- input ---
up = st.file_uploader("Upload a lyrics .txt file, or paste below", type=["txt"])
if up is not None and ss.upload_id != (up.name, up.size):
    ss.upload_id = (up.name, up.size)
    ss.lyrics = up.getvalue().decode("utf-8", errors="replace").lstrip("﻿")
    ss.before_prep = None
    ss.prep_msgs = []

st.text_area("Lyrics", key="lyrics", height=340,
             placeholder="[Title]\nSong name\n\n[Verse 1]\nFirst line | translation\n…")

# --- step 1: Claude ---
st.header("1 · Fix pronouns & translate (optional)")
st.caption("Uses Claude to change 你→祢 / 他→祂 where the text refers to God, and to "
           "add translations to lines that don't have one yet. Translations you "
           "already wrote are kept.")

c1, c2 = st.columns(2)
with c1:
    st.checkbox("Fix reverence pronouns", value=True, key="opt_pronouns")
    st.checkbox("Add missing translations", value=True, key="opt_translate")
    st.checkbox("Convert to Traditional Chinese", value=False, key="opt_traditional")
with c2:
    st.selectbox("Other language in your songs", ["Dutch", "English", "Other…"], key="opt_other")
    if ss.opt_other == "Other…":
        st.text_input("Language name", key="opt_other_custom", placeholder="e.g. German")

needs_claude = ss.opt_pronouns or ss.opt_translate
if needs_claude and APP_PASSWORD:
    st.text_input("Password", type="password", key="password",
                  help="Ask the person who shared this page for the password.")

b1, b2, _ = st.columns([1, 1, 2])
with b1:
    st.button("Run", type="primary", on_click=run_prep, use_container_width=True,
              disabled=not ss.lyrics.strip())
with b2:
    st.button("Undo", on_click=undo_prep, use_container_width=True,
              disabled=ss.before_prep is None)
if needs_claude and HAS_KEY:
    st.caption(f"Claude runs left today (shared by everyone): {runs_left()} / {DAILY_LIMIT}")

for kind, msg in ss.prep_msgs:
    getattr(st, kind)(msg)

# --- step 2: build ---
st.header("2 · Download the ProPresenter file")
st.caption("Adjust fonts and sizes in the sidebar (tap **>** at the top left on a phone).")


def build(text, cfg):
    notes = io.StringIO()
    with contextlib.redirect_stderr(notes):
        pres = make_pro.build_presentation(None, text, cfg)
    return pres, [n.removeprefix("note: ") for n in notes.getvalue().splitlines() if n.strip()]


if ss.lyrics.strip():
    try:
        pres, notes = build(ss.lyrics, cfg)
    except Exception as e:
        st.error(f"Could not build the presentation: {e}")
    else:
        if len(pres.cues) == 0:
            st.warning("No slides found. Make sure lyrics are under a tag like "
                       "`[Verse 1]` or `[Chorus]`.")
        else:
            name = pres.name if pres.name and pres.name != "Generated Song" else "song"
            fname = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "song"
            groups = ", ".join(g.group.name for g in pres.cue_groups)
            st.write(f"**{pres.name}** — {len(pres.cues)} slides ({groups})")
            st.download_button("⬇ Download .pro file", data=pres.SerializeToString(),
                               file_name=f"{fname}.pro", mime="application/octet-stream",
                               type="primary")
            if not make_pro._HAS_PYPINYIN:
                st.warning("pypinyin is not installed on the server, so no pinyin was added.")
        for n in notes:
            st.info(n)
        st.caption("In ProPresenter, drag the downloaded file into your Library "
                   "(or use **File → Import**).")
else:
    st.info("Paste or upload lyrics above to get started.")
