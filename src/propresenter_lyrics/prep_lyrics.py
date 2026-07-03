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

# shared deterministic tag handling (works as a script and when installed)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _tags

MODEL_DEFAULT = "claude-sonnet-4-6"

SYSTEM = """You are a meticulous editor of Chinese Christian worship lyrics and a \
careful translator. You make only the changes you are asked for and you never \
add commentary."""


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
            "你/你的/你們/你们 -> 祢, and third person 他/她/它/牠 -> 祂. Apply this to "
            "ALL Chinese in the file: lyric lines, the song title under [Title], "
            "and any Chinese you produce as a translation. This is a church "
            "songbook, so treat 你/他 as referring to God by default; only keep "
            "你/他 unchanged when it clearly refers to people (e.g. 你们要彼此相爱).")
    if do_translate:
        rules.append(
            f"2. TRANSLATION: append ' | ' then a natural, singable translation:\n"
            f"   - a Chinese line            -> add its {other_lang} translation\n"
            f"   - a non-Chinese line (e.g. {other_lang} or English) -> add its "
            f"Chinese translation (use reverence pronouns 祢/祂 in that Chinese "
            f"where it refers to God)\n"
            f"   - LINE BREAKS: if the source lyric contains '//' (a manual line "
            f"break), split it on '//', translate each part, and join your "
            f"translation with '//' at the SAME positions so the breaks line up. "
            f"Do not add '//' where the source has none.\n"
            f"   If a line ALREADY contains ' | ' with a translation, keep that "
            f"existing translation unchanged -- do not add, remove, or move any "
            f"'//' in it (still apply pronoun fixes to any Chinese part).")
    rules_block = "\n".join(rules)

    return f"""Transform the worship-lyrics file below.

{rules_block}

STRICT OUTPUT RULES:
- Output the WHOLE file, same line order, nothing else (no explanations, no code fences).
- Keep the section HEADER lines exactly as-is: lines like [Title], [Verse 1],
  [Chorus | #cc0033]. The song title text under [Title] is NOT translated (no
  ' | '), but DO apply the reverence-pronoun fix to it.
- Keep blank lines exactly where they are.
- A "lyric section" is one whose tag is a normal song part (Verse, Chorus,
  Bridge, Pre-Chorus, Intro, Outro, Tag, etc.). Any other section (e.g.
  [youtube], [ccli], [key], [note]) is metadata: leave its content completely
  unchanged -- do not translate or alter URLs, numbers, or notes.
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
        lyrics, tag_warnings = _tags.correct_tags(lyrics)
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
