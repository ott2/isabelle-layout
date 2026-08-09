"""`session_theories` must load an entry's in-entry import *closure*, not
just its ROOT-declared roots — and the classifier must draw the
in-entry / cross-entry / infrastructure line correctly.

This pins the fix for the AFP under-count: an entry that declares a few leaf
theories and pulls the rest in via `imports` (AODV declares 1, builds 73)
was previously loaded as just the declared roots.  The closure follows every
in-entry import style Isabelle allows — bare (`Mid`), self-qualified
(`Demo.SelfQual`), and relative path (`"sub/Leaf"`, `"../Base"`) — while
skipping cross-entry (`Other.Foo`) and base-library (`Main`,
`HOL-Library.FuncSet`) references, and excluding orphan `.thy` files that no
declared root imports.

The classifier is tested through its private name.  It is private on purpose
(deciding what counts as "infrastructure" is an analysis judgement, not a
reading of a file), but it is *load-bearing* on purpose too: the closure above
cannot be bounded without it, so the line it draws still needs pinning.
"""

from __future__ import annotations

import pytest

from isabelle_layout import parse_root_sessions, session_theories
from isabelle_layout.theories import _classify_import


# One entry `Demo` exercising every import style, plus an orphan.
#   Top   -> Mid, Main(infra)
#   Mid   -> "sub/Leaf"(path), Demo.SelfQual(self-qualified)
#   Leaf  -> "../Base"(path up), Other.Foo(cross-entry)
#   Base  -> "HOL-Library.FuncSet"(infra)
#   SelfQual -> Base
#   Orphan-> Base           (present on disk, imported by nobody reachable)
DEMO = {
    "Demo/ROOT": 'session Demo = HOL +\n  directories "sub"\n  theories\n    Top\n',
    "Demo/Top.thy": "theory Top imports Mid Main begin\nend\n",
    "Demo/Mid.thy": 'theory Mid imports "sub/Leaf" Demo.SelfQual begin\nend\n',
    "Demo/sub/Leaf.thy": 'theory Leaf imports "../Base" Other.Foo begin\nend\n',
    "Demo/Base.thy": 'theory Base imports "HOL-Library.FuncSet" begin\nend\n',
    "Demo/SelfQual.thy": "theory SelfQual imports Base begin\nend\n",
    "Demo/Orphan.thy": "theory Orphan imports Base begin\nend\n",
}


@pytest.fixture
def demo(tmp_path, write_tree):
    """The `Demo` entry on disk, and its single parsed session."""
    write_tree(tmp_path, DEMO)
    (session,) = parse_root_sessions(tmp_path / "Demo" / "ROOT")
    return tmp_path, session


# ------------------------------------------------------------------- closure

def test_closure_reaches_every_in_entry_style(demo):
    _root, session = demo
    stems = {p.stem for _n, p in session_theories(session)}
    # Top's declared root + bare, self-qualified, and both path imports.
    assert stems == {"Top", "Mid", "Leaf", "SelfQual", "Base"}


def test_orphan_theory_is_excluded(demo):
    _root, session = demo
    stems = {p.stem for _n, p in session_theories(session)}
    assert "Orphan" not in stems  # on disk, imported by nobody


def test_follow_imports_false_gives_declared_only(demo):
    _root, session = demo
    stems = {p.stem for _n, p in session_theories(session, follow_imports=False)}
    assert stems == {"Top"}  # just the ROOT-declared root


def test_no_duplicate_paths(demo):
    # Base is reached via two paths (Leaf's "../Base" and SelfQual's Base);
    # it must appear exactly once.
    _root, session = demo
    paths = [p.resolve() for _n, p in session_theories(session)]
    assert len(paths) == len(set(paths))


# ---------------------------------------------------------------- classifier

def test_bare_in_entry(demo):
    _root, session = demo
    kind, path = _classify_import("Mid", session)
    assert kind == "in_entry"
    assert path is not None


def test_self_qualified_is_in_entry(demo):
    _root, session = demo
    kind, path = _classify_import("Demo.SelfQual", session)
    assert kind == "in_entry"
    assert path.stem == "SelfQual"


def test_relative_path_is_in_entry(demo):
    root, session = demo
    importer = root / "Demo" / "sub" / "Leaf.thy"
    kind, path = _classify_import('"../Base"', session, importer=importer)
    assert kind == "in_entry"
    assert path.stem == "Base"


def test_cross_entry_qualified_skipped(demo):
    _root, session = demo
    kind, path = _classify_import("Other.Foo", session)
    assert kind == "cross_entry"
    assert path is None


def test_infra_bare_and_qualified_skipped(demo):
    _root, session = demo
    assert _classify_import("Main", session)[0] == "infra"
    assert _classify_import("HOL-Library.FuncSet", session)[0] == "infra"


def test_path_import_cannot_escape_entry(demo):
    # A path climbing above the entry root resolves to no in-entry theory
    # (containment guard), so it is not followed.
    root, session = demo
    importer = root / "Demo" / "Top.thy"
    kind, _path = _classify_import('"../../secret"', session, importer=importer)
    assert kind != "in_entry"
