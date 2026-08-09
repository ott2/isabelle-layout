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
"""

# The single source of the version; pyproject.toml reads it from here
# (`[tool.hatch.version]`).  Kept in the package rather than stated statically
# in pyproject so that `isabelle_layout.__version__` is correct when the package
# is imported from a source tree that was never installed.  Deriving it from
# `importlib.metadata` instead would raise `PackageNotFoundError` in exactly
# that case.
__version__ = "0.1.0"

__all__ = ["__version__"]
