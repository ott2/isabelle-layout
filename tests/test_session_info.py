"""`SessionInfo` is public, so what it promises is a test rather than a hope.

The [session-info] decision.  Four of the ten public functions take or return
this type, so it could not have been private without making most of the API
unusable — a type you cannot name is one you cannot annotate, store, or write
a helper around.  That makes it a compatibility surface forever, and the
useful question is not whether it is public but *what about it* is promised.

Promised: attribute access under these names, with these types, plus
`session_dir`, plus construction by keyword.  Not promised: dataclass-ness,
equality, ordering, hashing, `repr`, field *order*, or mutability.

This file tests exactly the promises.  It deliberately does **not** assert
that `SessionInfo == SessionInfo` compares field-wise, even though today it
does, because asserting it would convert an implementation detail into the
guarantee the docstring says it is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from isabelle_layout import SessionInfo, parse_root_sessions


# name -> the type its value must have, for a fully-populated session.
PROMISED = {
    "name": str,
    "root_path": Path,
    "in_subdir": str,
    "parent": str,
    "used_sessions": list,
    "directories": list,
    "theories": list,
}

# Every clause a session may carry, spelled the way Isabelle's own grammar
# admits it (`src/Pure/Build/sessions.scala`, `Parsers.session_entry`):
# a session-level `in`, block options in `[...]`, a `(global)` annotation on a
# theory, and a path-valued theory name.  Checked against that grammar rather
# than against what this parser happens to accept.
FULL_ROOT = (
    'session Demo in "src" = HOL +\n'
    '  description \\<open>everything at once\\<close>\n'
    '  options [document = false]\n'
    '  sessions\n    Other\n'
    '  directories "extra"\n'
    '  theories [document = false]\n'
    '    Top\n'
    '    Main (global)\n'
    '    "extra/Deep"\n'
)


@pytest.fixture
def full_session(tmp_path, write_tree):
    write_tree(tmp_path, {"ROOT": FULL_ROOT})
    (session,) = parse_root_sessions(tmp_path / "ROOT")
    return session


@pytest.mark.parametrize("attr, typ", sorted(PROMISED.items()))
def test_every_promised_attribute_is_present_and_typed(full_session, attr, typ):
    assert isinstance(getattr(full_session, attr), typ)


def test_the_promised_values_are_what_the_root_declares(full_session):
    assert full_session.name == "Demo"
    assert full_session.in_subdir == "src"
    assert full_session.parent == "HOL"
    assert full_session.used_sessions == ["Other"]
    assert full_session.directories == ["extra"]
    # `(global)` and `[document = false]` are annotations, not theory names:
    # bracketed and parenthesised groups are skipped wholesale, so neither
    # `global` nor `document` becomes a phantom theory.
    assert full_session.theories == [
        ("Top", None), ("Main", None), ("extra/Deep", None)]


def test_the_dir_override_slot_is_always_none(full_session):
    """Isabelle has no per-theory `in` clause, so nothing can fill this.

    `theory_entry = position(theory_name) ~ opt_keyword(GLOBAL)` — that is the
    whole of it (`src/Pure/Build/sessions.scala`).  `in` appears in the ROOT
    grammar only after a session name and inside `document_files (in ...)`.
    A scan of 979 real ROOTs across the AFP and the distribution finds the
    word inside a `theories` stanza 15 times, every one of them in a comment.

    The slot stays because it is public shape, and pinning it as always-None
    is what stops someone "fixing" it into a dialect Isabelle would reject.
    """
    assert all(override is None for _name, override in full_session.theories)


def test_session_dir_honours_the_in_clause(full_session):
    assert full_session.session_dir == full_session.root_path.parent / "src"


def test_session_dir_without_an_in_clause_is_the_roots_own_directory(
        tmp_path, write_tree):
    write_tree(tmp_path, {"ROOT": "session Plain = HOL +\n"})
    (session,) = parse_root_sessions(tmp_path / "ROOT")
    assert session.in_subdir is None
    assert session.session_dir == tmp_path.resolve()


def test_construction_by_keyword_needs_only_the_four_required_fields():
    """The promise that lets a consumer build one for a test or a synthetic
    session.  New fields, if ever added, arrive with defaults and are
    appended, so this call keeps compiling."""
    s = SessionInfo(name="S", root_path=Path("/tmp/ROOT"),
                    in_subdir=None, parent="HOL")
    assert s.used_sessions == []
    assert s.directories == []
    assert s.theories == []


def test_the_collection_defaults_are_not_shared_between_instances():
    # `field(default_factory=list)` rather than `= []`.  Sharing them would
    # make one parsed session's theories appear in another's, which is the
    # sort of thing that shows up as a wrong answer three call sites away.
    a = SessionInfo(name="A", root_path=Path("/tmp/ROOT"),
                    in_subdir=None, parent=None)
    b = SessionInfo(name="B", root_path=Path("/tmp/ROOT"),
                    in_subdir=None, parent=None)
    a.theories.append(("X", None))
    assert b.theories == []


def test_root_path_is_absolute(tmp_path, write_tree, monkeypatch):
    """Promised as a `Path`, and resolved — consumers key on it and join
    against it, and a relative one would mean different things depending on
    where the process happened to be standing."""
    write_tree(tmp_path, {"ROOT": "session S = HOL +\n"})
    monkeypatch.chdir(tmp_path)
    (session,) = parse_root_sessions(Path("ROOT"))
    assert session.root_path.is_absolute()
    assert session.root_path == (tmp_path / "ROOT").resolve()
