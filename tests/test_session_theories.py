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


def test_a_session_keeps_a_theory_named_like_a_distribution_logic(
        tmp_path, write_tree):
    """`[infra-shadow]`.  A bare name that resolves to a file the session owns
    *is* that file, whatever it is called.

    `src/CCL` is a session named `CCL` whose `Term.thy` imports `CCL`, meaning
    `CCL/CCL.thy`.  Consulting the hardcoded infrastructure name list before
    trying to resolve the name discarded it, and with it everything reachable
    only through it — 6 theories across `CCL`, `Cube` and `Sequents`.
    """
    write_tree(tmp_path, {
        "CCL/ROOT": "session CCL = Pure +\n  theories\n    Term\n",
        "CCL/Term.thy": "theory Term imports CCL begin\nend\n",
        "CCL/CCL.thy": "theory CCL imports Gfp begin\nend\n",
        "CCL/Gfp.thy": "theory Gfp imports Pure begin\nend\n",
    })
    (session,) = parse_root_sessions(tmp_path / "CCL" / "ROOT")
    stems = {p.stem for _n, p in session_theories(session)}
    assert stems == {"Term", "CCL", "Gfp"}  # not just {"Term"}


def test_a_bare_name_that_resolves_nowhere_is_still_infrastructure(demo):
    # The other half of the same change: dropping the name-list shortcut must
    # not make `Main` in-entry for an entry that has no `Main.thy`.
    _root, session = demo
    assert _classify_import("Main", session)[0] == "infra"
    assert _classify_import("Pure", session)[0] == "infra"


def test_the_closure_follows_a_directories_entry_outside_the_session_dir(
        tmp_path, write_tree):
    """`[session-dirs]`.  The `directories` clause is part of where a
    session's theories live, so the index that resolves bare imports has to
    cover it.

    `HOL-ODE-Numerics` declares `in "Numerics"` and
    `directories "../Refinement"`; indexing only the session directory left
    its bare imports into `../Refinement` unresolvable, and the load set was
    not closed — `Refinement/Autoref_Misc.thy` was reached by relative path
    while the `Refine_Dflt_No_Comp` it imports by bare name was not.
    """
    write_tree(tmp_path, {
        "Entry/ROOT": 'session Num in "Numerics" = HOL +\n'
                      '  directories "../Refinement"\n'
                      '  theories\n    Top\n',
        "Entry/Numerics/Top.thy": 'theory Top imports "../Refinement/Mid" begin\nend\n',
        "Entry/Refinement/Mid.thy": "theory Mid imports Deep begin\nend\n",
        "Entry/Refinement/Deep.thy": "theory Deep imports Main begin\nend\n",
    })
    (session,) = parse_root_sessions(tmp_path / "Entry" / "ROOT")
    stems = {p.stem for _n, p in session_theories(session)}
    # `Deep` is reached only by a bare import from a file in a declared
    # directory that sits outside the session directory.
    assert stems == {"Top", "Mid", "Deep"}


def test_a_directories_entry_may_leave_the_root_directory(tmp_path, write_tree):
    """`[session-dirs]`.  A `directories` entry is *not* confined to the ROOT's
    own directory, because Isabelle does not confine it.

    The fix for `[session-dirs]` was proposed with a guard rejecting any entry
    outside the ROOT directory, on the reasoning that it mirrors the
    containment `_classify_import` applies to relative-path imports and stops a
    malformed ROOT reaching into a neighbour.  Put to `isabelle build -n`, the
    ROOT below builds: `info.dirs` is ``dir :: directories`` with no
    containment (`Pure/Build/sessions.scala`), so the guard would drop
    `Neighbour` and reintroduce the reported bug in a rarer shape.

    What actually prevents a session reaching into a neighbour is enforced
    globally instead: Isabelle maps each canonical directory to one session and
    errors ``Duplicate use of directory`` if two claim the same one, so the
    corpus the guard defends against is one `isabelle build` refuses.

    No ROOT in the AFP or the distribution declares such an entry (0 of 153),
    so this is pinned by construction rather than by corpus.
    """
    write_tree(tmp_path, {
        "EntryA/ROOT": 'session A in "Sub" = HOL +\n'
                       '  directories\n    "../../Shared"\n'
                       '  theories\n    T\n',
        "EntryA/Sub/T.thy": "theory T imports Neighbour begin end\n",
        "Shared/Neighbour.thy": "theory Neighbour imports Main begin end\n",
    })
    (session,) = parse_root_sessions(tmp_path / "EntryA" / "ROOT")
    stems = {p.stem for _n, p in session_theories(session)}
    assert stems == {"T", "Neighbour"}


def test_an_absolute_directories_entry_is_honoured(tmp_path, write_tree):
    """`[session-dirs]`, the absolute case, which the relative one implies
    but does not state.

    Raised as a hardening question — a ROOT naming ``directories "/"`` makes
    this package scan from the filesystem root — and answered the same way as
    its sibling above, by asking rather than reasoning:

        $ isabelle build -n -l -d /tmp/absdir/Entry A
        Session Unsorted/A
          /tmp/absdir/Shared/Neighbour.thy

    Isabelle accepts the entry and loads through it, so a reader that
    rejected absolute entries would report fewer theories than the build for
    a legal ROOT — the same fault, in a rarer shape, that declined the
    confinement guard above.  The breadth of the scan is therefore a
    *caller's* concern, not a parser's: this package reports what the file
    declares, and `README.md` says so under **Reading untrusted projects**.
    """
    shared = tmp_path / "Shared"
    write_tree(tmp_path, {
        "Entry/ROOT": 'session A = HOL +\n'
                      f'  directories\n    "{shared}"\n'
                      '  theories\n    Neighbour\n',
        "Shared/Neighbour.thy": "theory Neighbour imports Main begin end\n",
    })
    (session,) = parse_root_sessions(tmp_path / "Entry" / "ROOT")
    assert session.directories == [str(shared)]
    assert [p for _n, p in session_theories(session)] == [shared / "Neighbour.thy"]


def test_path_import_cannot_escape_entry(demo):
    # A path climbing above the entry root resolves to no in-entry theory
    # (containment guard), so it is not followed.
    root, session = demo
    importer = root / "Demo" / "Top.thy"
    kind, _path = _classify_import('"../../secret"', session, importer=importer)
    assert kind != "in_entry"
