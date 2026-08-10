"""What structure does this Isabelle project have, according to its own files?

Sessions, theory headers, project roots — read from ``ROOT`` files and ``.thy``
headers, with no Isabelle process involved.  Nothing here starts a prover,
builds a heap, or needs one to have been built: the answers come from the text
the project itself commits.

The code is not new.  It was ``isabelle_query.common`` — 1,015 lines inside an
11,000-line querying tool — and every consumer that wanted a ROOT parser had to
install a query CLI to get one, inheriting its release cadence and its
userbase's compatibility constraints.  That is a distribution problem, not a
code problem, so the fix is a door rather than a rewrite.  See ``README.md``.

The public API
--------------

Named below, and named by *evidence*: these are the functions the twelve
scripts across two repositories actually import, in descending order of how
often they do it.  Everything else in this package is private and stays
changeable.

    iter_sessions            8    default_t_dir            4
    resolve_session_theory   4    iter_thy_files           4
    parse_root_sessions      3    session_theories         2
    resolve_base_logic       2    discover_roots           1

plus :func:`~isabelle_layout.theories.parse_thy_imports`, which the query tool
itself imports, and :class:`~isabelle_layout.roots.SessionInfo`, which four of
those functions take or return and so cannot be private.

The failure being avoided is the one that produced this package.  ``common``
was a private-sounding name doing public work, so every import felt like
reaching into internals and nothing could be changed without guessing at who
might be relying on it.  Exporting the whole module "for now" is how that
happens; hence a list, and hence a leading underscore on everything else.

`isabelle_layout.distribution` is deliberately **not** re-exported here
--------------------------------------------------------------------

:func:`~isabelle_layout.distribution.is_hol_base` and
:func:`~isabelle_layout.distribution.is_known_nonhol_base` are public, but you
import them from that module by name::

    from isabelle_layout.distribution import is_hol_base

They answer a different kind of question — a fact about the Isabelle
distribution's hardcoded object-logic names, not about the project being read —
and a hardcoded list of session names ages differently from a parser.  Making
the import say so is the cheapest way to keep the difference visible at the
call site, which is where it matters.
"""

from __future__ import annotations

from .project import default_t_dir
from .roots import (
    SessionInfo,
    discover_roots,
    iter_sessions,
    parse_root_sessions,
    resolve_base_logic,
    resolve_session_theory,
)
from .theories import (
    iter_thy_files,
    parse_thy_imports,
    session_theories,
)

# The single source of the version; pyproject.toml reads it from here
# (`[tool.hatch.version]`).  Kept in the package rather than stated statically
# in pyproject so that `isabelle_layout.__version__` is correct when the package
# is imported from a source tree that was never installed.  Deriving it from
# `importlib.metadata` instead would raise `PackageNotFoundError` in exactly
# that case.
__version__ = "0.2.0"

__all__ = [
    "SessionInfo",
    "default_t_dir",
    "discover_roots",
    "iter_sessions",
    "iter_thy_files",
    "parse_root_sessions",
    "parse_thy_imports",
    "resolve_base_logic",
    "resolve_session_theory",
    "session_theories",
    "__version__",
]
