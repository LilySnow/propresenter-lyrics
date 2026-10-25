# propresenter-lyrics

Generate **ProPresenter 7** (`.pro`) presentations from plain lyrics text — with
automatic pinyin, bilingual layout, reverence-pronoun handling, and
Simplified→Traditional conversion. Built for Chinese / Dutch / English worship
teams, but useful for any multilingual lyrics.

Three commands:

- **`pp-make`** — turns a lyrics text file into a `.pro` (deterministic, offline).
- **`pp-preview`** — the same slides as an HTML page you can open in any
  browser, to check them without ProPresenter (offline, self-contained).
- **`pp-prep`** — optional pre-pass that uses Claude to fix reverence
  pronouns and add translations, plus deterministic tag-typo fixing and
  Simplified→Traditional conversion.

There is also a [web interface](webapp/) for people who don't use a terminal.

Validated against ProPresenter **21.4**.

## Install

Not on PyPI — install straight from GitHub (this pulls in everything, including
the `pp-prep` dependencies):

```bash
pip install git+https://github.com/LilySnow/propresenter-lyrics.git
```

Or from a clone (handy if you want the example config and source at hand):

```bash
git clone https://github.com/LilySnow/propresenter-lyrics.git
cd propresenter-lyrics
pip install -e .
```

`pp-prep` needs an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# lyrics already final (pronouns + translations done):
pp-make song.txt -o ~/Downloads/song.pro

# let Claude fix pronouns / translate / convert, then build, in one pipe:
pp-prep song.txt | pp-make -o ~/Downloads/song.pro

# check the slides in a browser first (writes song.html next to song.txt):
pp-preview song.txt
```

- Input: a file, or `-` for stdin (`pp-make` also reads stdin when you omit the
  filename, as in the pipe above).
- `pp-make` and `pp-preview` take `--config` (see [Configuration](#configuration))
  and `--title` to override the song title.
- `pp-prep` translates Chinese lines into Dutch, and every other line into
  Chinese. Use `--other English` (or any language) to change what Chinese lines
  are translated into. Translations you already wrote are kept. Other options:
  `--no-translate`, `--no-pronouns`, `--no-traditional`, `--dry-run`
  (see `pp-prep --help`).

### How it fits together

`slide_layout.py` decides what goes on each slide (sections, pages, pinyin,
fonts, sizes, positions) and knows nothing about ProPresenter. `make_pro.py`
writes that layout as a `.pro` file; `preview.py` draws the same layout as HTML.
Because both start from `slide_layout.layout_song()`, the preview always shows
the same slide breaks and text as the `.pro`:

```python
from propresenter_lyrics import slide_layout, make_pro, preview
song = slide_layout.layout_song(text, slide_layout.load_config())
pro_bytes = make_pro.write_presentation(song).SerializeToString()
html = preview.render_html(song)
```

## Lyrics file format

```
[Title]
使我们合一

[Verse 1]
求主留我於十架//在彼有生命水 | Heer, houd mij dicht bij het kruis//Daar stroomt het water
在你的爱里面 | In uw liefde

[youtube]
https://youtu.be/xxxx
```

- `[Title]` — song name, shown small in a corner and used as the document name.
- `[Verse 1]`, `[Chorus 2]`, … — coloured groups. Numbers are preserved, and
  typos such as `[Chrous]` are corrected automatically. Give a section its own
  colour with `[Bridge | #8800cc]`.
- **Translation separator:** ` | ` (also accepts full-width `｜` and similar bars).
- **`//` inside a line** = line break; **`//` on its own line** = page break.
  Default is one lyric line per page.
- **Chinese line** → PINYIN on top, 中文, translation below.
  **Dutch/English line** → primary, Chinese translation below (no pinyin).
- **Metadata / custom tags:** only standard ProPresenter group tags (Verse,
  Chorus, Bridge, Pre-Chorus, Intro, Outro, Tag, …) become slides. **Any other
  tag** (e.g. `[youtube]`, `[ccli]`, `[key]`) is automatically ignored — its
  content never appears in the `.pro`, no configuration needed. `pp-make`
  prints a `note:` to stderr for each skipped section so a mistyped group tag
  doesn't vanish silently.

## Configuration

All fonts, sizes, outline, margins, lyrics position (top / middle / bottom),
title position and markers live in a **YAML** config (commented, easy to edit).
Fonts are set once for Chinese and once for Latin text (pinyin, Dutch/English,
title):

```yaml
fonts:
  chinese: PingFang SC     # or PingFang TC, Songti SC, Heiti SC, Hiragino Sans GB, ...
  latin: Helvetica Neue    # or Arial, Avenir Next, Futura, Gill Sans, Georgia, ...
```

The template lists the fonts that come with every Mac. ProPresenter can only show
fonts installed on the computer that runs it. Create a config you can edit with:

```bash
pp-make --init-config                 # ~/.config/propresenter-lyrics/config.yaml
pp-make --init-config ./config.yaml   # or in your working folder
```

`pp-make` and `pp-preview` search for a config in this order (first found wins; otherwise
built-in defaults apply):

1. `--config PATH`
2. `./config.yaml` (or `.yml` / `.json`) in the current directory
3. `~/.config/propresenter-lyrics/config.yaml`

JSON is also accepted if you prefer it. See the commented [`config.template.yaml`](src/propresenter_lyrics/config.template.yaml).

## Recompiling the ProPresenter format (rarely needed)

The compiled format modules live in `src/propresenter_lyrics/proto/` and are
frozen, so the tool keeps working even if upstream changes. If a future
ProPresenter version changes the `.pro` format, regenerate them:

```bash
bash scripts/compile_protos.sh
```

Proto definitions are reverse-engineered by the community project
[greyshirtguy/ProPresenter7-Proto](https://github.com/greyshirtguy/ProPresenter7-Proto).

## Notes

- Reverence pronouns (你→祢, 他→祂 for God) and translations are
  theology-sensitive — review `pp-prep` output before generating slides.
- Multi-size rows and text stroke render from proto attributes; verify on a copy
  of your library first.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
