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
"""

from __future__ import annotations

import os
from pathlib import Path


MARKER_NAME = ".isabelle-query"


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


def default_t_dir(start: Path | None = None) -> Path:
    """Resolve the Isabelle session directory to index.

    Resolution order:

    1. ``$ISABELLE_QUERY_ROOT``, if set (``~`` expanded, resolved to absolute).
    2. The nearest project marker file (``.isabelle-query``) at or above
       ``start`` (default: the current working directory).  Drop one at a
       project's root, committed to the repo, so the tool resolves the
       right session directory from anywhere in the tree with no flags.
       Its first non-blank, non-comment line names the session dir
       (relative to the marker); an empty marker means "the root is my
       own directory".
    3. The nearest directory that holds a ``ROOT`` file directly — an
       unambiguous single session, so most projects need no marker.
    4. Fall back to ``start`` itself; its theories are then discovered by
       scanning for ROOT files beneath it.

    Discovery deliberately does *not* infer a multi-session parent from
    child ``ROOT`` files: a directory holding several ROOTs may be one
    project's sessions or several unrelated projects (e.g. vendored
    copies), and a structural scan can't tell them apart — that is what
    the marker file (or ``--root`` / ``$ISABELLE_QUERY_ROOT``) resolves.  This
    replaces the old hard-coded ``PROJECT_ROOT/t``: the tool assumes no
    particular directory name, and no longer expects to live in a sibling
    ``bin/`` of the project it queries.
    """
    env = os.environ.get("ISABELLE_QUERY_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        marker = d / MARKER_NAME
        if marker.is_file():
            named = _read_marker(marker)
            return named if named is not None else d
    for d in (here, *here.parents):
        if (d / "ROOT").is_file():
            return d
    return here
