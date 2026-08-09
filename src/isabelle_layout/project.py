"""project.py — where the project is, before anything is parsed.

Every other module in this package takes a directory and reads what is in it.
This one answers the question that comes first: *which* directory?  It is
filesystem search rather than parsing, and it is the only part of the package
that consults the environment, which is why it sits alone.

The resolution order is a hierarchy of decreasing authority — an explicit
environment variable, then a committed marker file, then an unambiguous `ROOT`
on disk, then the caller's own starting point.  A default is a last resort,
not a first guess.

Discovery deliberately does *not* infer a multi-session parent from child
`ROOT` files.  A directory holding several ROOTs may be one project's sessions
or several unrelated projects (a vendored copy, a checkout of the AFP beside
your own work), and no structural scan can tell those apart.  That ambiguity
is exactly what a marker file resolves, by being committed: the project states
its own layout instead of the tool guessing at it.

Two names, and why  [marker-name]
---------------------------------

The marker was `.isabelle-query`, named after the one tool that read it.  In a
neutral package that is a wart, and a wart that hardens fast: every project
that drops the file makes it more expensive to change, and two already have it
committed (`~/projects/43sp`, `~/projects/claudecode/ndtht`).  So a neutral
name (`.isabelle-layout`, `$ISABELLE_LAYOUT_ROOT`) is primary, and the
historical one is read as an alias for as long as it takes those projects to
migrate — which is to say, indefinitely, at no cost, since it is four extra
`stat` calls per directory level.

Two things this could have got wrong, and does not:

**Nearest directory wins, not neutral-name-anywhere-wins.**  Searching the
whole ancestor chain for `.isabelle-layout` and only then searching it again
for `.isabelle-query` would let a distant new-style marker outrank a nearby
old-style one.  Both names are therefore checked *at each level* before moving
up.  A project's own marker always beats an ancestor's, whichever spelling
each happens to use — because the question the walk is answering is "which
project am I standing in", and that is a question about distance.

**A third name is not free.**  `isabelle-watchdog` already keeps
`.isabelle-watchdog`, deliberately symmetric with `.isabelle-query` — same
shape, same search, same place — but it holds *different content* (where build
records go, not where theories live), so it is genuinely a second file rather
than a second spelling of this one.  Adding `.isabelle-layout` alongside is
only justified because the name `.isabelle-query` makes a false claim about
who the file is for.

How far up to look  [root-bound]
--------------------------------

The upward walk is unbounded by default and bounded on request: ``bound=``,
not a policy baked into the search.

Unbounded suits a query tool, where overshooting yields an empty index and an
obviously wrong answer.  It does not suit every caller.
`isabelle_watchdog.corpus.find_marker` runs the same search deliberately
stopped at the project root, and its reason is worth repeating because it is
about consequences rather than tidiness: a wrong *session* directory produces
a visibly wrong answer, whereas a wrong *log* directory **creates a dataset in
it** and pools two repositories' trajectories into one corpus.  Projects nest
routinely (`~/projects/claudecode/ndtht` inside `~/projects/claudecode`), so a
stray marker in a shared parent must not capture every repository beneath it.

Those two callers want different searches, and neither is wrong.  A library
that picks one is a library the other stops using — so the bound is a
parameter and the caller states which it wants.

What ``bound`` is *not* is a git dependency.  The obvious convenience would be
``bound="git-toplevel"``, resolved by shelling out.  That would put a
subprocess in the import path of a parsing library with no runtime
dependencies, to answer a question the caller already knows the answer to.
The caller computes the boundary and passes a `Path`; policy stays with the
policy-maker.

The environment overrides are **not** subject to the bound.  Setting
``$ISABELLE_LAYOUT_ROOT`` is an explicit instruction from the operator, and a
search boundary is a guard against accidental discovery, not a sandbox.
"""

from __future__ import annotations

import os
from pathlib import Path


# The neutral name, and the historical one it replaces.  Order matters: within
# a single directory the neutral spelling wins, so a project mid-migration can
# carry both and have the new one be authoritative.
MARKER_NAME = ".isabelle-layout"
LEGACY_MARKER_NAME = ".isabelle-query"
MARKER_NAMES = (MARKER_NAME, LEGACY_MARKER_NAME)

# Likewise for the environment override.  `$ISABELLE_QUERY_ROOT` is honoured
# because shell profiles, Makefiles and CI configs already set it, and a split
# that silently stopped reading it would break the projects it is meant to
# serve on the day it shipped.
ENV_ROOT = "ISABELLE_LAYOUT_ROOT"
LEGACY_ENV_ROOT = "ISABELLE_QUERY_ROOT"
ENV_ROOTS = (ENV_ROOT, LEGACY_ENV_ROOT)


def _read_marker(marker: Path) -> Path | None:
    """Return the session directory named by a project marker file,
    resolved relative to the marker's own location.

    The first non-blank, non-comment (``#``) line is taken as the path;
    ``~`` is expanded and a relative path is resolved against the
    marker's directory.  Returns None if the file names nothing usable
    (empty or all comments), in which case the caller treats the marker's
    own directory as the root.
    """
    try:
        lines = marker.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = Path(s).expanduser()
        if not p.is_absolute():
            p = marker.parent / p
        return p.resolve()
    return None


def _search_chain(start: Path, bound: Path | None) -> list[Path]:
    """``start`` and its ancestors, stopping at ``bound`` inclusive.

    A ``bound`` that is not an ancestor of ``start`` yields ``[start]`` alone.
    That is the conservative reading of the request, and the safe one: the
    caller has said "do not leave this project", so discovering that we are
    not in it is a reason to stop looking rather than a reason to ignore the
    instruction and wander.  (`isabelle_watchdog.corpus.find_marker` resolves
    the same case the same way.)
    """
    chain = [start, *start.parents]
    if bound is None:
        return chain
    stop = bound.resolve()
    return chain[:chain.index(stop) + 1] if stop in chain else [start]


def _find_marker(start: Path, bound: Path | None = None) -> Path | None:
    """The nearest project marker at or above ``start``, either spelling.

    Both names are tested at each level before moving up, so proximity beats
    spelling: a project's own `.isabelle-query` outranks an ancestor's
    `.isabelle-layout`.  See the module docstring.
    """
    for d in _search_chain(start, bound):
        for name in MARKER_NAMES:
            marker = d / name
            if marker.is_file():
                return marker
    return None


def default_t_dir(start: Path | None = None, *,
                  bound: Path | None = None) -> Path:
    """Resolve the Isabelle session directory to index.

    Resolution order:

    1. ``$ISABELLE_LAYOUT_ROOT``, else ``$ISABELLE_QUERY_ROOT``, if set
       (``~`` expanded, resolved to absolute).
    2. The nearest project marker file — ``.isabelle-layout``, or the
       historical ``.isabelle-query`` — at or above ``start`` (default: the
       current working directory).  Drop one at a project's root, committed to
       the repo, so the tool resolves the right session directory from
       anywhere in the tree with no flags.  Its first non-blank, non-comment
       line names the session dir (relative to the marker); an empty marker
       means "the root is my own directory".
    3. The nearest directory that holds a ``ROOT`` file directly — an
       unambiguous single session, so most projects need no marker.
    4. Fall back to ``start`` itself; its theories are then discovered by
       scanning for ROOT files beneath it.

    ``bound``, if given, is a directory the upward searches in steps 2 and 3
    will not climb above (inclusive).  It does not constrain step 1: an
    environment variable is an explicit instruction, and the bound guards
    against accidental discovery rather than sandboxing a deliberate choice.
    Pass it when overshooting would be *costly* rather than merely wrong —
    see the module docstring under ``[root-bound]``.

    Discovery deliberately does *not* infer a multi-session parent from
    child ``ROOT`` files: a directory holding several ROOTs may be one
    project's sessions or several unrelated projects (e.g. vendored
    copies), and a structural scan can't tell them apart — that is what
    the marker file (or an explicit root argument / the environment
    variable) resolves.
    """
    for var in ENV_ROOTS:
        env = os.environ.get(var)
        if env:
            return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    marker = _find_marker(here, bound)
    if marker is not None:
        named = _read_marker(marker)
        return named if named is not None else marker.parent
    for d in _search_chain(here, bound):
        if (d / "ROOT").is_file():
            return d
    return here
