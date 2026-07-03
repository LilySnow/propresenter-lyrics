# propresenter-lyrics

Generate **ProPresenter 7** (`.pro`) presentations from plain lyrics text — with
automatic pinyin, bilingual layout, reverence-pronoun handling, and
Simplified→Traditional conversion. Built for Chinese / Dutch / English worship
teams, but useful for any multilingual lyrics.

Two commands:

- **`make_pro`** — turns a lyrics text file into a `.pro` (deterministic, offline).
- **`prep_lyrics`** — optional pre-pass that uses Claude to fix reverence
  pronouns and add translations, plus deterministic tag-typo fixing and
  Simplified→Traditional conversion.

Validated against ProPresenter **21.4**.

## Install

Not on PyPI — install straight from GitHub (this pulls in everything, including
the `prep_lyrics` dependencies):

```bash
pip install git+https://github.com/LilySnow/propresenter-lyrics.git
```

Or from a clone (handy if you want the example config and source at hand):

```bash
git clone https://github.com/LilySnow/propresenter-lyrics.git
cd propresenter-lyrics
pip install -e .
```

`prep_lyrics` needs an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# lyrics already final (pronouns + translations done):
make_pro song.txt -o ~/Downloads/song.pro

# let Claude fix pronouns / translate / convert, then build, in one pipe:
prep_lyrics song.txt | make_pro -o ~/Downloads/song.pro
```

Both read a file, or stdin when you omit the filename.

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
- `[Verse 1]`, `[Chorus 2]`, … — coloured groups. Numbers are preserved; typos
  are auto-corrected by `prep_lyrics`.
- **Translation separator:** ` | ` (also accepts full-width `｜` and similar bars).
- **`//` inside a line** = line break; **`//` on its own line** = page break.
  Default is one lyric line per page.
- **Chinese line** → PINYIN on top, 中文, translation below.
  **Dutch/English line** → primary, Chinese translation below (no pinyin).
- **Metadata / custom tags:** only standard ProPresenter group tags (Verse,
  Chorus, Bridge, Pre-Chorus, Intro, Outro, Tag, …) become slides. **Any other
  tag** (e.g. `[youtube]`, `[ccli]`, `[key]`) is automatically ignored — its
  content never appears in the `.pro`, no configuration needed. `make_pro`
  prints a `note:` to stderr for each skipped section so a mistyped group tag
  doesn't vanish silently.

## Configuration

All fonts, sizes, stroke, title position, and markers live in a **YAML** config
(commented, easy to edit). Create one you can edit with:

```bash
make_pro --init-config                 # ~/.config/propresenter-lyrics/config.yaml
make_pro --init-config ./config.yaml   # or in your working folder
```

`make_pro` searches for a config in this order (first found wins; otherwise
built-in defaults apply):

1. `--config PATH`
2. `./config.yaml` (or `.yml` / `.json`) in the current directory
3. `~/.config/propresenter-lyrics/config.yaml`

JSON is also accepted if you prefer it. See [`config.example.yaml`](config.example.yaml).

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
  theology-sensitive — review `prep_lyrics` output before generating slides.
- Multi-size rows and text stroke render from proto attributes; verify on a copy
  of your library first.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
