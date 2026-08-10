"""The demonstration command, and the rule that decides when it is finished.

`[demo-cli]`.  The command exists to be a runnable use of the public API, so
the interesting test is not that it prints the right thing — it is that it
*reaches every public name*.  That criterion is what makes it a test of the
API rather than of the implementation: a surface with a name no plausible
consumer needs shows up here as a flag with no reason to exist, and a surface
missing something shows up as a private import.

The rest of the file pins the behaviours a consumer would notice: exit status,
the two views, and the one diagnostic the command offers that the library does
not (a ROOT declaring a theory with no file on disk).
"""

from __future__ import annotations

import ast
from importlib.metadata import distribution
from pathlib import Path

import pytest

import isabelle_layout
from isabelle_layout import _cli


TINY = {
    "Proj/ROOT": 'session Proj = HOL +\n'
                 '  directories "sub"\n'
                 '  theories\n    Top\n',
    "Proj/Top.thy": 'theory Top imports "sub/Leaf" begin\nend\n',
    "Proj/sub/Leaf.thy": "theory Leaf imports Main begin\nend\n",
}


@pytest.fixture
def proj(tmp_path, write_tree):
    write_tree(tmp_path, TINY)
    return tmp_path


# ------------------------------------------------------------ the design rule

def test_the_demonstration_touches_every_public_name():
    """Every name in `__all__`, plus both distribution predicates, is imported
    *and* referenced by the command.

    Imported alone would not do: a name can be imported and never used, which
    is exactly the "exported for now" failure the public-API test exists to
    prevent, reappearing one layer up.
    """
    tree = ast.parse(Path(_cli.__file__).read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            imported.update(a.asname or a.name for a in node.names)
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

    promised = set(isabelle_layout.__all__) | {
        "is_hol_base", "is_known_nonhol_base", "conformance"}

    assert promised - imported == set(), "not imported by the demonstration"
    assert promised - referenced == set(), "imported but never used"


def test_no_private_name_was_needed():
    """If the command had to reach past the public surface, the surface would
    be wrong and that would be the finding.  It did not."""
    tree = ast.parse(Path(_cli.__file__).read_text(encoding="utf-8"))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            reached.update(a.name for a in node.names)
    assert {n for n in reached if n.startswith("_") and n != "__version__"} == set()


def test_the_console_script_is_declared_by_the_installed_package():
    """The entry point is metadata, so it is only real once installed —
    the same reason the suite runs against a wheel rather than the source tree."""
    eps = {e.name: e.value for e in distribution("isabelle-layout").entry_points}
    assert eps.get("isabelle-layout") == "isabelle_layout._cli:main"


# ------------------------------------------------------------------ behaviour

def test_detail_view_reports_declared_and_built(proj, capsys):
    assert _cli.main([str(proj)]) == 0
    out = capsys.readouterr().out
    assert "Proj" in out
    assert "1 theory   Top" in out        # what the ROOT declares
    assert "builds       2 theories" in out  # what it actually loads


def test_no_closure_omits_the_expensive_answer(proj, capsys):
    assert _cli.main([str(proj), "--no-closure"]) == 0
    out = capsys.readouterr().out
    assert "declared" in out
    assert "builds" not in out


def test_list_view_is_tabular_and_skips_the_closure(proj, capsys):
    assert _cli.main([str(proj), "--list"]) == 0
    out = capsys.readouterr().out
    assert "SESSION" in out and "PARENT" in out
    assert "builds" not in out


def test_verbose_lists_theories_with_their_imports(proj, capsys):
    assert _cli.main([str(proj), "-v"]) == 0
    out = capsys.readouterr().out
    assert "Leaf" in out
    assert "imports  Main" in out


def test_a_declared_theory_with_no_file_is_flagged(tmp_path, write_tree, capsys):
    """The ROOT claims `Ghost`; nothing on disk provides it.  Isabelle would
    refuse to build this, and a reader that silently returned one theory
    instead of two would give a plausible, short answer."""
    write_tree(tmp_path, {
        "P/ROOT": "session P = HOL +\n  theories\n    Real\n    Ghost\n",
        "P/Real.thy": "theory Real imports Main begin\nend\n",
    })
    assert _cli.main([str(tmp_path)]) == 0
    assert "no file on disk: Ghost" in capsys.readouterr().out


def test_roots_and_files_list_paths(proj, capsys):
    assert _cli.main([str(proj), "--roots"]) == 0
    assert capsys.readouterr().out.strip().endswith("Proj/ROOT")
    assert _cli.main([str(proj), "--files"]) == 0
    assert capsys.readouterr().out.strip().endswith("Top.thy")


def test_finding_nothing_exits_one(tmp_path, capsys):
    assert _cli.main([str(tmp_path)]) == 1
    assert "no Isabelle sessions found" in capsys.readouterr().out


def test_a_missing_path_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _cli.main([str(tmp_path / "nope")])
    assert exc.value.code == 2


def test_self_check_verifies_the_shipped_corpus(capsys):
    """End-to-end over package *data*: on an installed wheel this fails if
    `conformance.json` did not ship, which importing the code would not."""
    assert _cli.main(["--self-check"]) == 0
    out = capsys.readouterr().out
    assert "agree" in out and "Isabelle" in out
