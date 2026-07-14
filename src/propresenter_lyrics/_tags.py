"""Shared, deterministic tag handling for make_pro and prep_lyrics.

Fix typos in section tags first (so [chrous 1] -> [Chorus 1]); only *genuinely*
non-standard tags (e.g. [youtube]) are then treated as metadata by make_pro.
"""

import re
import difflib

# canonical spellings used for typo/case correction
CANON_TAGS = ["Title", "Pre-Chorus", "Verse", "Chorus", "Post-Chorus", "Bridge",
              "Intro", "Outro", "Ending", "Tag", "Instrumental", "Interlude",
              "Vamp", "Refrain", "Coda"]
_CANON_LOWER = {t.lower(): t for t in CANON_TAGS}

# tags treated as the song title (its text is the title, not a slide group)
TITLE_TAGS = {"title", "标题", "標題", "歌名"}

# standard ProPresenter group tags (match on first word, lower-cased) that
# become slides. Anything else is metadata and skipped by make_pro.
GROUP_TAGS = {
    "intro", "verse", "pre-chorus", "prechorus", "chorus", "post-chorus",
    "postchorus", "bridge", "tag", "instrumental", "ending", "outro",
    "interlude", "vamp", "breakdown", "turnaround", "re-intro", "reintro",
    "misc", "blank", "refrain", "coda",
}

_CN_TAGS = {"标题", "標題", "歌名"}
_HEADER_RE = re.compile(r"^(\s*)[\[\u3010](.+?)[\]\u3011](\s*)$")  # ASCII [] or full-width 【】
_NUM_RE = re.compile(r"^(.*?)[\s]*?(\d+)?\s*$")   # optional trailing number


def correct_tags(text, cutoff=0.8):
    """Fix typos/casing in standard [Section] tags WITHOUT touching a trailing
    number. [chorus 1] -> [Chorus 1], [chrous1] -> [Chorus 1], [titel] -> [Title].
    Genuinely non-standard tags (metadata like [youtube]) are left unchanged.
    Returns (fixed_text, warnings)."""
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

        nm = _NUM_RE.match(name)                    # peel off trailing number
        alpha = nm.group(1).strip() if nm else name
        num = nm.group(2) if nm else None
        low = alpha.lower()

        new_alpha = None
        if low in _CN_TAGS or alpha in _CN_TAGS:
            pass
        elif low in _CANON_LOWER:
            new_alpha = _CANON_LOWER[low]           # normalise case
        else:
            match = difflib.get_close_matches(low, list(_CANON_LOWER), n=1, cutoff=cutoff)
            if match:
                new_alpha = _CANON_LOWER[match[0]]  # clear typo -> fix
            # else: non-standard tag (metadata) -> leave alone

        if new_alpha and (new_alpha != alpha or num is not None):
            fixed = new_alpha + (" " + num if num else "")
            if fixed != name:
                warnings.append("tag [%s] -> [%s]" % (name, fixed))
            name = fixed
        out.append("%s[%s%s]%s" % (m.group(1), name,
                                   (" " + rest) if rest else "", m.group(3)))
    return "\n".join(out), warnings
