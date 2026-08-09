"""The public surface is a promise, so it is pinned rather than described.

`isabelle_query.common` became hard to change because nobody could say what
was public: a private-sounding module doing public work, with twelve scripts
across two repositories reaching into it.  The fix is not "document the API",
which drifts; it is to make the surface a **test**, so adding to it is a
deliberate act and removing from it fails loudly.

`__all__` here is derived from evidence — what consumers actually import —
rather than from what looks tidy.  If this test fails, either a public name
was dropped (a breaking change, needing a version bump and a note) or one was
added without deciding it should be public (the failure mode this file exists
to catch).
"""

from __future__ import annotations

import importlib

import pytest

import isabelle_layout


# Exactly the names consumers import, plus `SessionInfo` (four of the others
# take or return it) and `parse_thy_imports` (the query tool imports it).
PUBLIC = {
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
}


def test_all_is_exactly_the_decided_surface():
    assert set(isabelle_layout.__all__) - {"__version__"} == PUBLIC


@pytest.mark.parametrize("name", sorted(PUBLIC))
def test_every_promised_name_is_importable(name):
    assert hasattr(isabelle_layout, name)


def test_version_is_exported_and_parseable():
    parts = isabelle_layout.__version__.split(".")
    assert len(parts) >= 2 and all(p.isdigit() for p in parts[:2])


def test_distribution_predicates_are_public_but_not_re_exported():
    """The [distribution-module] decision, as a test.

    `is_hol_base` is public — two consumers import it — but it answers a
    question about the *Isabelle distribution's* hardcoded names rather than
    about the project being read, and a hardcoded list of session names ages
    differently from a parser.  Keeping it off the top level makes the import
    line say which kind of claim the caller is relying on.
    """
    distribution = importlib.import_module("isabelle_layout.distribution")
    assert callable(distribution.is_hol_base)
    assert callable(distribution.is_known_nonhol_base)
    assert not hasattr(isabelle_layout, "is_hol_base")
    assert not hasattr(isabelle_layout, "is_known_nonhol_base")


def test_the_analysis_judgement_did_not_become_public():
    """`classify_import` decides what counts as "infrastructure", which is an
    opinion about a corpus rather than a reading of a file.  It moved across
    because `session_theories` cannot bound its walk without it, and it moved
    across *private*.  The evidence for that line: no consumer outside the
    query tool ever imported it."""
    assert not hasattr(isabelle_layout, "classify_import")
    theories = importlib.import_module("isabelle_layout.theories")
    assert not hasattr(theories, "classify_import")
    assert callable(theories._classify_import)


def test_run_guarded_did_not_come_along():
    """Six lines, not Isabelle-specific, already deprecated where it lived and
    already copied into `isabelle_watchdog.guard`.  A third home is how a
    utility becomes three subtly different utilities."""
    assert not hasattr(isabelle_layout, "run_guarded")
    for mod in ("project", "roots", "theories", "distribution", "_lexer"):
        m = importlib.import_module(f"isabelle_layout.{mod}")
        assert not hasattr(m, "run_guarded"), mod
