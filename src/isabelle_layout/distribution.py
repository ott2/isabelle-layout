"""distribution.py — facts about Isabelle, not about your project.

Everything else in this package reads a file and reports what it says.  This
module does not: it holds a hardcoded list of object logics that ship with
Isabelle, and answers whether a base logic is HOL-family.  That is a fact about
the *distribution*, and it is a different kind of thing.

The distinction is worth a whole module because the two kinds of knowledge
**age differently**.  A parser is wrong when Isabelle's grammar changes, which
is rare, visible, and breaks loudly.  A list of session names is wrong when
Isabelle adds or renames an object logic, which is quiet — the code keeps
running and simply classifies the new one as unknown.  Mixing the two would
mean a release cadence set by whichever ages faster, and a reader unable to
tell which sort of claim they were relying on.

So: separate module, separate import, and the asymmetry between the two
predicates below is deliberate rather than accidental.  They ask complementary
questions and default in *opposite* directions, because they are used in
opposite situations:

  - :func:`is_hol_base` requires positive *HOL* evidence.  Use it where a
    wrong "yes" mis-applies a HOL-specific table; an unrecognised base is
    flagged rather than silently treated as HOL.
  - :func:`is_known_nonhol_base` requires positive *non-HOL* evidence.  Use it
    where HOL is the sensible default and only a recognised other logic should
    opt out; an unrecognised base stays on the default path.

Neither is the negation of the other, and swapping them silently inverts what
happens to a base logic nobody has heard of.  The unknown case is the point:
one of these has to hand it to the safe side, and which side is safe depends
on the caller.

The base logic itself comes from
:func:`isabelle_layout.roots.resolve_base_logic`, which is *structural* — it
follows a session's declared parent chain, so it stays in the parser half of
the package.  Only the naming of the result lives here.
"""

from __future__ import annotations


def is_hol_base(base: str) -> bool:
    """Whether a base logic (a `resolve_base_logic` root) is HOL-family.

    Stated as a HOL **allowlist**: every HOL session name begins `HOL` (`HOL`,
    `HOL-Library`, `HOL-Analysis`, and HOL-with-a-ZF-flavour like `HOL-ZF`);
    `Pure`, `ZF`/`ZF-*`, `FOL`, `CTT`, … are other object logics.  An
    unrecognised base is therefore treated as **non-HOL** — flagged, never
    silently HOL — which is the safe direction when the answer gates a
    HOL-specific table (the notation table behind `const_canon_est`, the census
    union): over-restrict rather than mis-apply.
    """
    return base.startswith("HOL")


# The Isabelle-distribution object logics that are *not* HOL — the non-HOL bases a
# `resolve_base_logic` root can name.  Recognisable by name even from a single
# session's scope (their names are stable distribution ids, unlike an arbitrary
# in-corpus parent session), which is what makes `is_known_nonhol_base` robust
# where `is_hol_base` cannot reach the root (a cross-session parent out of scope).
# These are the exact non-HOL sessions declared `= Pure +` in the Isabelle2025-2
# src tree (FOL, ZF, HOL, … are all siblings on the Pure meta-logic; FOL is *not*
# HOL-based); `Pure` itself is the meta-logic.  ZF and FOL variants (`ZF-*`,
# `FOLP`) are caught by prefix in `is_known_nonhol_base`.
_NONHOL_DISTRIBUTION_BASES = frozenset({
    "Pure", "FOL", "FOLP", "CTT", "Sequents", "CCL", "Cube", "LCF"})


def is_known_nonhol_base(base: str) -> bool:
    """Whether a base logic is a **positively identified** non-HOL object logic.

    The complement of :func:`is_hol_base`'s question, and it defaults the *other*
    way: `is_hol_base` requires positive HOL evidence (for a HOL-only table that
    must never mis-apply), whereas this requires positive *non-HOL* evidence — so
    an unknown base (e.g. an out-of-scope parent *session* name like
    `Multitape_TM_Substrate`, reached under ``-R <sub-session>``) is **not** flagged
    non-HOL.  Use this where HOL is the sensible default and only a known non-HOL
    logic should opt out (the interactive namespace fallback): matches `Pure`,
    `ZF`/`ZF-*`, `FOL`/`FOLP`, `CTT`, `Sequents`, …; leaves everything else to the
    HOL default."""
    return (base in _NONHOL_DISTRIBUTION_BASES
            or base.startswith("ZF") or base.startswith("FOL"))
