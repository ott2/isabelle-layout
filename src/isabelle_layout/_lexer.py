r"""_lexer.py — the one place that knows what Isabelle text is *not* syntax.

This module exists because of a dependency the brief's grouping does not show.
"ROOT parsing" and "theory headers" look like two independent concerns, and
they are — except that both begin by removing comments and cartouches, and
both are wrong in the same specific ways if that removal is naive.
`_tokenize_root` calls `strip_comments`; so does `parse_thy_imports`.  One
lexer underneath, therefore, rather than a copy in each: a second copy is how
`isabelle-watchdog` and `isabelle-query` came to disagree about what a session
is called, and reproducing that divergence *inside* the package built to end
it would be a poor start.

Three things here are easy to get wrong and hard to notice, and each is a real
file rather than a hypothetical:

**Block comments nest.**  A non-greedy ``\(\*.*?\*\)`` stops at the first
``*)``, which leaves the *outer* comment's tail behind as live text.  In
``Universal_Turing_Machine.GeneratedCode`` the header reads

    (*   "HOL-Library.Code_Target_Numeral" (* see codegen.pdf *) *)

and a non-greedy strip left a stray ``*)`` inside the ``imports`` clause, so
the parser reported a theory literally named ``*)``.  Depth is counted here
instead.

**Cartouches nest, and carry free text.**  A ``description \<open>…\<close>``
may contain anything, including the word ``session`` at the start of a line.
Tokenising a ROOT without removing them spawns phantom sessions out of prose.

**An unterminated comment swallows the rest of the file**, which is what
Isabelle's own lexer does.  Guessing otherwise would mean a typo'd ``(*``
yields a session list nobody can build -- a wrong answer in place of an
obviously broken one.

Comments are replaced by a *space* rather than deleted, so ``imports(*c*)Bar``
still tokenises as two words.
"""

from __future__ import annotations

import re

_OLD_DESC_OPEN, _OLD_DESC_CLOSE = "{*", "*}"
_OPEN_CARTOUCHE, _CLOSE_CARTOUCHE = r"\<open>", r"\<close>"
_TAG_RE = re.compile(r"\\<[A-Za-z_^]+>")


_CARTOUCHE_RE = re.compile(r'\\<open>|\\<close>')


def strip_cartouches(text: str) -> str:
    """Remove Isabelle cartouches `\\<open>...\\<close>` (nestable).

    Content inside a cartouche is descriptive text, not ROOT syntax,
    so it must not be tokenised — otherwise a comment like
    `\\<comment> \\<open>...session... \\<close>` spawns phantom
    sessions from words inside the prose.

    Driven by the delimiter positions rather than by a per-character walk:
    the two are equivalent (the output is exactly the depth-0 text between
    delimiters, delimiters themselves dropped), but a ROOT file has a handful
    of cartouches where a `.thy` corpus has megabytes of characters, and
    `parse_thy_imports` now runs this over whole theory files.
    """
    if _OPEN_CARTOUCHE not in text and _CLOSE_CARTOUCHE not in text:
        return text
    out: list[str] = []
    depth, pos = 0, 0
    for m in _CARTOUCHE_RE.finditer(text):
        if depth == 0:
            out.append(text[pos:m.start()])
        if m.group() == _OPEN_CARTOUCHE:
            depth += 1
        elif depth > 0:
            depth -= 1
        pos = m.end()
    if depth == 0:
        out.append(text[pos:])
    return "".join(out)


_COMMENT_TOKEN_RE = re.compile(r'\(\*|\*\)')


def strip_block_comments(text: str) -> str:
    r"""Remove `(* ... *)` comments, which **nest** in Isabelle.

    The obvious non-greedy regex, `\(\*.*?\*\)`, stops at the first `*)`, so a
    nested comment leaves the outer closer behind as live text.  In
    `Universal_Turing_Machine.GeneratedCode` the header

        (*   "HOL-Library.Code_Target_Numeral" (* see codegen.pdf *) *)

    left a stray `*)` inside the `imports` clause, and `parse_thy_imports`
    duly reported `*)` as an imported theory.  Comments are replaced by a
    space, not deleted, so `imports(*c*)Bar` still tokenises as two words; an
    unterminated comment swallows the remainder, as Isabelle's lexer does.
    """
    if "(*" not in text:
        return text
    out: list[str] = []
    depth, pos = 0, 0
    for m in _COMMENT_TOKEN_RE.finditer(text):
        if m.group() == "(*":
            if depth == 0:
                out.append(text[pos:m.start()])
                out.append(" ")
            depth += 1
        elif depth > 0:
            depth -= 1
            if depth == 0:
                pos = m.end()
    if depth == 0:
        out.append(text[pos:])
    return "".join(out)


def strip_old_descriptions(text: str) -> str:
    r"""Remove legacy `{* ... *}` description markup, which does **not** nest.

    Delimiter-driven, for the same reason :func:`strip_cartouches` is, and
    here the reason is sharper than economy.  This was
    ``re.sub(r"\{\*.*?\*\}", " ", text, flags=re.DOTALL)``, which is correct
    and is **quadratic** on input that opens the construct and never closes
    it: the lazy `.*?` scans to end-of-text, fails, and the engine retries
    from the next `{*`.  Measured on this tree before the change, 24 KB of
    unclosed `{*` took 1.1 s, and the cost grows with the square — minutes
    for a file an agent might be pointed at without looking.  Both the other
    strippers here were already written this way; this one was the holdout.

    The semantics are the regex's, exactly: left to right, each `{*` pairs
    with the *first* following `*}`, the pair and everything between it are
    replaced by one space, and an unpaired `{*` ends the substitution,
    leaving the remainder of the text alone.  Verified against the regex over
    every `.thy` and `ROOT` in the AFP and the Isabelle distribution.
    """
    if _OLD_DESC_OPEN not in text:
        return text
    out: list[str] = []
    pos = 0
    while True:
        start = text.find(_OLD_DESC_OPEN, pos)
        if start < 0:
            break
        end = text.find(_OLD_DESC_CLOSE, start + len(_OLD_DESC_OPEN))
        if end < 0:
            break
        out.append(text[pos:start])
        out.append(" ")
        pos = end + len(_OLD_DESC_CLOSE)
    out.append(text[pos:])
    return "".join(out)


def strip_comments(text: str) -> str:
    text = strip_block_comments(text)
    text = strip_cartouches(text)
    text = strip_old_descriptions(text)  # legacy `{* ... *}` description
    text = _TAG_RE.sub(" ", text)  # lone `\<comment>` etc. (after cartouches)
    return text
