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

```bash
pip install propresenter-lyrics            # make_pro
pip install "propresenter-lyrics[prep]"    # + prep_lyrics (Claude + OpenCC)
```

Or from source:

```bash
git clone https://github.com/YOUR_USERNAME/propresenter-lyrics.git
cd propresenter-lyrics
pip install -e ".[prep]"
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
- **Metadata sections** listed in `ignore_sections` (e.g. `[youtube]`, `[ccli]`)
  are skipped — their content never appears in the `.pro`.

## Configuration

All fonts, sizes, stroke, title position, markers, and ignored sections live in
`config.json`. `make_pro` looks for it in this order:

1. `--config PATH`
2. `./config.json` (current directory)
3. `~/.config/propresenter-lyrics/config.json`
4. the packaged default

Copy the default from `src/propresenter_lyrics/config.json`, edit, and drop it in
your working dir or `~/.config/propresenter-lyrics/`.

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
