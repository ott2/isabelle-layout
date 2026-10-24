r"""Input this package did not author, and must not be surprised by.

Every file read here is written by somebody else.  In the case this library
was built for — a tool, or an agent, pointed at a repository that merely
*carries* Isabelle proofs — "somebody else" is not necessarily someone the
caller has any reason to trust, and the call volume is whatever the tool
decides.  So the properties below are not about getting the right answer on
good input, which the rest of the suite covers.  They are about three ways
the wrong input used to produce something worse than a wrong answer: a
`UnicodeDecodeError` out of a public function, a parse that took minutes, and
a read with no ceiling on it.

None of this makes a hostile ROOT *safe* to act on.  What a ROOT declares is
still whatever its author wrote, and `[session-dirs]` means a `directories`
entry may legitimately point outside the tree — Isabelle accepts that and
loads from it, so this package reports it.  Containment, if a caller needs
it, is the caller's to impose; see `README.md`.
"""

from __future__ import annotations

import re
import time

import pytest

from isabelle_layout import (
    discover_roots,
    default_t_dir,
    iter_sessions,
    parse_root_sessions,
    parse_thy_imports,
    session_theories,
)
from isabelle_layout._lexer import strip_old_descriptions
from isabelle_layout.project import read_text_bounded
from isabelle_layout.roots import (
    _MAX_ROOT_BYTES,
    _parse_root_directories,
    _parse_root_theories,
)
from isabelle_layout.theories import _MAX_HEADER_BYTES

# Enough of the construct to take over a second before the fix, and ~0.0 ms
# after.  The bound is deliberately loose: it is here to catch a return to
# quadratic behaviour, not to measure a machine.
_SLOW_BUDGET_S = 2.0


# --------------------------------------------------------------------------
# Undecodable bytes reach a public function and do not raise
# --------------------------------------------------------------------------

def test_a_root_of_invalid_utf8_parses_instead_of_raising(tmp_path):
    """`parse_root_sessions` was already hardened; its neighbours were not.

    A bare `Path.read_text()` raises `UnicodeDecodeError` on bytes that are
    not valid UTF-8, and decodes with the *locale's* encoding otherwise — so
    one stray file aborted an enumeration, and the same tree could parse
    differently on two machines.
    """
    root = tmp_path / "ROOT"
    root.write_bytes(b'session Foo = HOL +\n  theories \xff\xfe Bar\n')

    sessions = parse_root_sessions(root)
    assert [s.name for s in sessions] == ["Foo"]
    assert sessions[0].theories == [("Bar", None)]


def test_the_line_oriented_root_parsers_survive_invalid_utf8(tmp_path):
    """One theory per line, which is what these two read; the undecodable
    line is simply not an identifier, so it is skipped rather than fatal."""
    root = tmp_path / "ROOT"
    root.write_bytes(b'session Foo = HOL +\n  theories\n    \xff\xfe\n    Bar\n')

    assert _parse_root_theories(root) == ["Bar"]
    assert _parse_root_directories(root) == []


def test_an_undecodable_roots_index_does_not_abort_discovery(tmp_path):
    """The `ROOTS` index is read while walking, so one bad file used to take
    down the whole walk rather than the directory it sits in."""
    (tmp_path / "ROOTS").write_bytes(b"\xff\xfe sub\n")
    (tmp_path / "ROOT").write_text("session A = HOL +\n")

    assert discover_roots(tmp_path) == [tmp_path / "ROOT"]
    assert [s.name for s in iter_sessions(tmp_path)] == ["A"]


def test_an_undecodable_marker_file_does_not_raise(tmp_path):
    """`[marker-name]`.  The marker is read at *each level* of the upward
    walk, so an undecodable one anywhere above the start used to raise."""
    (tmp_path / ".isabelle-layout").write_bytes(b"# \xff\xfe\n")
    # Names nothing usable, so the marker's own directory is the root.
    assert default_t_dir(tmp_path) == tmp_path.resolve()

    # And when the undecodable bytes are *not* commented out they are a
    # (useless) directory name, which is the documented reading of the first
    # non-blank line.  The property under test is that it is read at all.
    other = tmp_path / "sub"
    other.mkdir()
    (other / ".isabelle-layout").write_bytes(b"\xff\xfe\n")
    assert default_t_dir(other).parent == other.resolve()


def test_a_thy_of_invalid_utf8_yields_imports(tmp_path):
    thy = tmp_path / "T.thy"
    thy.write_bytes(b'theory T imports \xff\xfe Main begin end\n')
    assert "Main" in parse_thy_imports(thy)


# --------------------------------------------------------------------------
# The strippers are linear, and unchanged in what they strip
# --------------------------------------------------------------------------

_OLD_DESC_RE = re.compile(r"\{\*.*?\*\}", re.DOTALL)


@pytest.mark.parametrize("text", [
    "", "{*", "*}", "{*}", "{**}", "{* a *}", "{* a {* b *}", "{* a *} {* b",
    "{{**}}", "*}{*", "{*\n\n*}", "{* *} *} {*", "x{*y*}z",
    "{*" * 50, "*}" * 50, "no markup here",
])
def test_strip_old_descriptions_matches_the_regex_it_replaced(text):
    """The function is the regex's semantics, written so as not to backtrack.

    Kept as a test rather than a comment because the equivalence is the whole
    licence for the change: left to right, each `{*` pairs with the *first*
    following `*}`, the pair and its contents become one space, and an
    unpaired `{*` ends the substitution.
    """
    assert strip_old_descriptions(text) == _OLD_DESC_RE.sub(" ", text)


def test_unclosed_old_description_markup_is_not_quadratic():
    """600 KB of `{*` that never closes.

    The lazy `.*?` this replaced scanned to end-of-text once per `{*`: 24 KB
    measured at 1.1 s, and growing with the square.
    """
    text = "{* " * 200_000
    start = time.perf_counter()
    strip_old_descriptions(text)
    assert time.perf_counter() - start < _SLOW_BUDGET_S


def test_a_header_that_never_closes_is_not_quadratic(tmp_path):
    """`theory X imports Y` repeated, with no `begin`, `keywords` or
    `abbrevs` anywhere — so `_THY_HEADER_RE` can never match, and used to
    rescan to end-of-file from every `theory` token in it."""
    thy = tmp_path / "Hostile.thy"
    thy.write_text("theory X imports Y " * 60_000)
    assert thy.stat().st_size > _MAX_HEADER_BYTES

    start = time.perf_counter()
    assert parse_thy_imports(thy) == []
    assert time.perf_counter() - start < _SLOW_BUDGET_S


# --------------------------------------------------------------------------
# Reads are bounded
# --------------------------------------------------------------------------

def test_read_text_bounded_stops_at_the_limit(tmp_path):
    p = tmp_path / "big"
    p.write_bytes(b"x" * 10_000)
    assert len(read_text_bounded(p, 100)) == 100


def test_a_truncated_multibyte_character_does_not_raise(tmp_path):
    """The limit is a byte count, so it can land inside a character."""
    p = tmp_path / "utf8"
    p.write_bytes("aé".encode("utf-8"))        # 'é' is two bytes
    assert read_text_bounded(p, 2) == "a�"


def test_a_header_beyond_the_read_bound_is_not_searched_for(tmp_path):
    """The bound is a real limit, not decoration.

    Measured over the AFP and the distribution, the deepest header in 11,931
    files ends at 10,372 bytes; the cap is six times that.  A header pushed
    past it is therefore not a file this package will meet, but the behaviour
    should still be "no imports found" rather than a partial one.
    """
    thy = tmp_path / "Deep.thy"
    thy.write_text(" " * (_MAX_HEADER_BYTES + 10) + "theory T imports Main begin")
    assert parse_thy_imports(thy) == []


def test_a_header_just_inside_the_read_bound_is_still_found(tmp_path):
    thy = tmp_path / "Shallow.thy"
    thy.write_text(" " * (_MAX_HEADER_BYTES - 200) + "theory T imports Main begin")
    assert parse_thy_imports(thy) == ["Main"]


def test_the_root_bound_is_far_above_any_real_root():
    """The largest ROOT in either corpus is the distribution's `HOL/ROOT`, at
    30 KB.  If this constant is ever lowered towards that, the margin is the
    thing to re-measure."""
    assert _MAX_ROOT_BYTES >= 32 * 30 * 1024


# --------------------------------------------------------------------------
# Structure that is hostile rather than malformed
# --------------------------------------------------------------------------

def test_a_cyclic_import_terminates(tmp_path):
    """Isabelle rejects cyclic imports; nothing stops a file declaring them,
    and `session_theories` follows imports transitively."""
    (tmp_path / "ROOT").write_text('session S = HOL +\n  theories A\n')
    (tmp_path / "A.thy").write_text("theory A imports B begin end\n")
    (tmp_path / "B.thy").write_text("theory B imports A begin end\n")

    session = parse_root_sessions(tmp_path / "ROOT")[0]
    names = sorted(n for n, _ in session_theories(session))
    assert names == ["A", "B"]


def test_a_self_importing_theory_terminates(tmp_path):
    (tmp_path / "ROOT").write_text('session S = HOL +\n  theories A\n')
    (tmp_path / "A.thy").write_text("theory A imports A begin end\n")

    session = parse_root_sessions(tmp_path / "ROOT")[0]
    assert [n for n, _ in session_theories(session)] == ["A"]
