#!/usr/bin/env python3
"""
prep_lyrics.py  --  preprocessing for Chinese/Dutch/English worship lyrics.

Pipeline (each step optional):
  (a) fix typos in [Section] tags, e.g. [titel]->[Title]   (deterministic, warns)
  (b) reverence pronouns: 你->祢, 他/她/它->祂 where they refer to God  (LLM)
  (d) add a translation only where one is missing; never change a translation
      you already supplied                                              (LLM)
  (c) convert Simplified -> Traditional, protecting 祢/祂           (deterministic)

Reads a file or stdin; writes stdout (default) or -o FILE. Warnings go to stderr
so the output can be piped straight into make_pro.py.

USAGE
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install anthropic pypinyin opencc
    python prep_lyrics.py song.txt --other Dutch | python make_pro.py - -o ~/Downloads/song.pro
    python prep_lyrics.py song.txt -o song_prepped.txt          # write a file instead
    python prep_lyrics.py song.txt --dry-run                    # show the LLM prompt, no API
    python prep_lyrics.py song.txt --no-traditional             # keep Simplified

Flags: --other LANG, --no-translate, --no-pronouns, --no-tag-fix,
       --no-traditional, --freeze-provided, --model, --dry-run.
Review the output before generating slides -- pronouns and translations are
theology-sensitive.
"""

import sys, os, argparse, re, difflib

MODEL_DEFAULT = "claude-sonnet-4-6"

SYSTEM = """You are a meticulous editor of Chinese Christian worship lyrics and a \
careful translator. You make only the changes you are asked for and you never \
add commentary."""

# ---- (a) tag typo correction --------------------------------------------
CANON_TAGS = ["Title", "Pre-Chorus", "Verse", "Chorus", "Bridge", "Intro",
              "Outro", "Ending", "Tag", "Refrain", "Interlude", "Vamp", "Coda"]
_CANON_LOWER = {t.lower(): t for t in CANON_TAGS}
_CN_TAGS = {"标题", "標題", "歌名"}
# non-lyric metadata tags that must never be "corrected" into a lyric tag
DEFAULT_IGNORE = ["youtube", "url", "link", "video", "ccli", "copyright",
                  "author", "key", "tempo", "bpm", "note", "notes", "comment",
                  "source"]
_HEADER_RE = re.compile(r"^(\s*)\[(.+?)\](\s*)$")
_NUM_RE = re.compile(r"^(.*?)[\s]*?(\d+)?\s*$")   # trailing number, optional


def correct_tags(text, ignore=None):
    """Fix typos/casing in [Section] tags WITHOUT touching a trailing number.
    [chorus 1] -> [Chorus 1], [chrous1] -> [Chorus 1], [titel] -> [Title].
    Tags in `ignore` (metadata like [youtube]) and unknown tags are left alone.
    Returns (fixed_text, warnings)."""
    ignore = set(w.lower() for w in (ignore if ignore is not None else DEFAULT_IGNORE))
    warnings, out = [], []
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if not m:
            out.append(line)
            continue
        inner = m.group(2)
        name, rest = (inner.split("|", 1)[0], "|" + inner.split("|", 1)[1]) \
            if "|" in inner else (inner, "")
        name = name.strip()

        # peel off a trailing number ("Chorus 1", "Chorus1") so we never lose it
        nm = _NUM_RE.match(name)
        alpha = nm.group(1).strip() if nm else name
        num = nm.group(2) if nm else None
        low = alpha.lower()

        new_alpha = None
        if low in ignore or low in _CN_TAGS or alpha in _CN_TAGS:
            pass                                       # metadata / valid CN tag
        elif low in _CANON_LOWER:
            new_alpha = _CANON_LOWER[low]              # just normalise case
        else:
            match = difflib.get_close_matches(low, list(_CANON_LOWER), n=1, cutoff=0.75)
            if match:
                new_alpha = _CANON_LOWER[match[0]]
            else:
                warnings.append("unrecognised tag [%s] (left unchanged)" % name)

        if new_alpha and (new_alpha != alpha or num is not None):
            fixed = new_alpha + (" " + num if num else "")
            if fixed != name:
                warnings.append("tag [%s] -> [%s]" % (name, fixed))
            name = fixed
        out.append("%s[%s%s]%s" % (m.group(1), name,
                                   (" " + rest) if rest else "", m.group(3)))
    return "\n".join(out), warnings


def _load_ignore():
    """Read ignore_sections from config.json (same search order as make_pro),
    falling back to DEFAULT_IGNORE."""
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.getcwd(), "config.json"),
                 os.path.expanduser("~/.config/propresenter-lyrics/config.json"),
                 os.path.join(here, "config.json")):
        if os.path.exists(cand):
            try:
                return json.load(open(cand, encoding="utf-8")).get(
                    "ignore_sections", DEFAULT_IGNORE)
            except Exception:
                break
    return DEFAULT_IGNORE


# ---- (c) Simplified -> Traditional --------------------------------------
try:
    import opencc as _opencc
    _CC = _opencc.OpenCC("s2t")
    _HAS_OPENCC = True
except Exception:
    _HAS_OPENCC = False


def to_traditional(text):
    """Convert Simplified -> Traditional, protecting reverence pronouns 祢/祂
    (which OpenCC would otherwise mangle, e.g. 祢 -> 禰)."""
    if not _HAS_OPENCC:
        return text, False
    prot = {"祢": "\ue000", "祂": "\ue001"}
    for k, v in prot.items():
        text = text.replace(k, v)
    text = _CC.convert(text)
    for k, v in prot.items():
        text = text.replace(v, k)
    return text, True


def build_prompt(lyrics, other_lang, do_pronouns, do_translate):
    rules = []
    if do_pronouns:
        rules.append(
            "1. REVERENCE PRONOUNS (Chinese text only): wherever a pronoun clearly "
            "refers to God / Jesus / the Holy Spirit, rewrite it -- second person "
            "你/你的/你們/你们 -> 祢, and third person 他/她/它/牠 -> 祂. This applies "
            "both to Chinese lyric lines AND to any Chinese you produce as a "
            "translation. If a pronoun refers to people, do NOT change it "
            "(e.g. 你们要彼此相爱 keeps 你们). When uncertain, leave it unchanged.")
    if do_translate:
        rules.append(
            f"2. TRANSLATION: append ' | ' then a natural, singable translation:\n"
            f"   - a Chinese line            -> add its {other_lang} translation\n"
            f"   - a non-Chinese line (e.g. {other_lang} or English) -> add its "
            f"Chinese translation (use reverence pronouns 祢/祂 in that Chinese "
            f"where it refers to God)\n"
            f"   If a line ALREADY contains ' | ' with a translation, keep that "
            f"existing translation unchanged (still apply pronoun fixes to any "
            f"Chinese part).")
    rules_block = "\n".join(rules)

    return f"""Transform the worship-lyrics file below.

{rules_block}

STRICT OUTPUT RULES:
- Output the WHOLE file, same line order, nothing else (no explanations, no code fences).
- Keep every section header line exactly as-is: lines like [Title], [Verse 1],
  [Chorus | #cc0033], and the title text under [Title]. Do not translate or
  alter headers or the title line.
- Keep blank lines exactly where they are.
- Leave metadata sections untouched: under headers like [youtube], [ccli],
  [key], [note], etc., do not translate or change URLs, numbers, or notes.
- Only lyric lines change. Each lyric line becomes:  original | translation
- Do not merge or split lines. One input lyric line -> one output lyric line.

FILE:
{lyrics}"""


def call_claude(prompt, model, max_tokens):
    import anthropic
    client = anthropic.Anthropic()        # reads ANTHROPIC_API_KEY from env
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def _is_header(line):
    s = line.strip()
    return s.startswith("[") and s.endswith("]")


def _split_pair(line, seps="|｜∣│"):
    idxs = [line.find(s) for s in seps if line.find(s) != -1]
    if idxs:
        i = min(idxs)
        return line[:i].rstrip(), line[i + 1:].strip()
    return line, None


def restore_provided_translations(original_text, llm_text, freeze=False):
    """Force-preserve translations the user already supplied.

    For every input lyric line that already had ' | translation', overwrite the
    LLM's translation with the original one. By default the LLM's (pronoun-fixed)
    left side is kept; with freeze=True the whole original line is restored,
    untouched. Returns (merged_text, aligned_ok).
    """
    o = original_text.splitlines()
    g = llm_text.splitlines()
    if len(o) != len(g):
        return llm_text, False          # line counts differ -> can't align safely
    out = []
    for ol, gl in zip(o, g):
        if ol.strip() and not _is_header(ol):
            _, otrans = _split_pair(ol)
            if otrans is not None:       # user provided a translation here
                if freeze:
                    out.append(ol)       # leave the original line entirely alone
                else:
                    gprimary, _ = _split_pair(gl)
                    out.append(gprimary.rstrip() + " | " + otrans)
                continue
        out.append(gl)
    return "\n".join(out), True


def main():
    ap = argparse.ArgumentParser(description="Fix tags/pronouns + translate lyrics via Claude")
    ap.add_argument("textfile", help="lyrics file, or '-' to read stdin")
    ap.add_argument("-o", "--out", default=None, help="output file (default: stdout)")
    ap.add_argument("--other", "--to", dest="other", default="Dutch",
                    help="the non-Chinese language in your songs (default Dutch). "
                         "Chinese lines get this language; lines in this language "
                         "get Chinese.")
    ap.add_argument("--no-translate", action="store_true", help="only fix pronouns")
    ap.add_argument("--no-pronouns", action="store_true", help="only translate")
    ap.add_argument("--no-tag-fix", action="store_true", help="skip [tag] typo correction")
    ap.add_argument("--no-traditional", action="store_true",
                    help="keep Simplified Chinese (default: convert to Traditional)")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--freeze-provided", action="store_true",
                    help="leave any line that already has '| translation' fully "
                         "untouched (no pronoun fix either)")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, do not call the API")
    args = ap.parse_args()

    do_translate = not args.no_translate
    do_pronouns = not args.no_pronouns
    if not do_translate and not do_pronouns and args.no_tag_fix and args.no_traditional:
        sys.exit("Nothing to do.")

    if args.textfile == "-":
        lyrics = sys.stdin.read()
    else:
        lyrics = open(os.path.expanduser(args.textfile), encoding="utf-8").read()

    # (a) deterministic tag typo correction (warnings to stderr)
    if not args.no_tag_fix:
        lyrics, tag_warnings = correct_tags(lyrics, ignore=_load_ignore())
        for w in tag_warnings:
            sys.stderr.write("WARNING: %s\n" % w)

    prompt = build_prompt(lyrics, args.other, do_pronouns, do_translate)
    if args.dry_run:
        print(prompt)
        return

    # (b + d) LLM: reverence pronouns + add translation only where missing
    if do_translate or do_pronouns:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...")
        result = strip_fences(call_claude(prompt, args.model, args.max_tokens))
        # deterministically protect translations the user already supplied
        result, aligned = restore_provided_translations(
            lyrics, result, freeze=args.freeze_provided)
        if not aligned:
            sys.stderr.write(
                "WARNING: output line count differed from input, so provided "
                "translations could not be force-preserved. Review the result.\n")
    else:
        result = lyrics

    # (c) Simplified -> Traditional (protecting 祢/祂)
    if not args.no_traditional:
        result, ok = to_traditional(result)
        if not ok:
            sys.stderr.write("WARNING: opencc not installed -> Simplified kept. "
                             "Run: pip install opencc\n")

    # (e) stdout by default so it can be piped into make_pro.py
    if args.out:
        out = os.path.expanduser(args.out)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(result + ("\n" if not result.endswith("\n") else ""))
        sys.stderr.write("Wrote %s\n" % out)
    else:
        sys.stdout.write(result + ("\n" if not result.endswith("\n") else ""))


if __name__ == "__main__":
    main()
