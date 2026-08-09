"""`default_t_dir`: which directory is the project, before anything is parsed.

Pins the [marker-name] decision — a neutral `.isabelle-layout` primary with
the historical `.isabelle-query` read as an alias — and in particular the part
of it that is easy to get subtly wrong: **proximity beats spelling**.  Both
names are tested at each level of the upward walk, so a project's own marker
always outranks an ancestor's, whichever spelling each happens to use.

The failure being guarded against is silent.  Search all the way up for the
new name first, and a stray `.isabelle-layout` three directories above
captures every repository beneath it, each of which had said perfectly clearly
where its own theories live.
"""

from __future__ import annotations

import pytest

from isabelle_layout import default_t_dir
from isabelle_layout.project import (
    ENV_ROOT,
    LEGACY_ENV_ROOT,
    LEGACY_MARKER_NAME,
    MARKER_NAME,
)


@pytest.fixture(autouse=True)
def no_ambient_env(monkeypatch):
    """Neither override leaks in from the developer's own shell.

    Both are real variables that real profiles set; a suite that inherited one
    would pass here and fail on a machine that did not.
    """
    monkeypatch.delenv(ENV_ROOT, raising=False)
    monkeypatch.delenv(LEGACY_ENV_ROOT, raising=False)


# ----------------------------------------------------------- the environment

def test_neutral_env_var_wins_over_everything(tmp_path, write_tree, monkeypatch):
    write_tree(tmp_path, {MARKER_NAME: "", "ROOT": "session S = HOL\n"})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv(ENV_ROOT, str(elsewhere))
    assert default_t_dir(tmp_path) == elsewhere.resolve()


def test_legacy_env_var_is_still_honoured(tmp_path, monkeypatch):
    # Shell profiles, Makefiles and CI configs already set this one.  A split
    # that stopped reading it would break its projects on the day it shipped.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv(LEGACY_ENV_ROOT, str(elsewhere))
    assert default_t_dir(tmp_path) == elsewhere.resolve()


def test_neutral_env_var_beats_the_legacy_one(tmp_path, monkeypatch):
    new, old = tmp_path / "new", tmp_path / "old"
    new.mkdir()
    old.mkdir()
    monkeypatch.setenv(ENV_ROOT, str(new))
    monkeypatch.setenv(LEGACY_ENV_ROOT, str(old))
    assert default_t_dir(tmp_path) == new.resolve()


def test_env_var_expands_a_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(ENV_ROOT, "~/proj")
    assert default_t_dir(tmp_path) == (tmp_path / "proj").resolve()


# --------------------------------------------------------------- the markers

@pytest.mark.parametrize("name", [MARKER_NAME, LEGACY_MARKER_NAME])
def test_either_spelling_is_found(tmp_path, write_tree, name):
    write_tree(tmp_path, {f"deep/sub/{name}": "", "deep/sub/ROOT": "session S\n"})
    start = tmp_path / "deep" / "sub" / "nested"
    start.mkdir()
    assert default_t_dir(start) == (tmp_path / "deep" / "sub").resolve()


def test_the_nearest_marker_wins_even_when_it_is_the_legacy_spelling(
        tmp_path, write_tree):
    """Proximity beats spelling.  This is the whole decision.

    Search the chain for the neutral name first and this test fails: the
    ancestor's `.isabelle-layout` captures a project that stated its own root
    perfectly clearly, one directory down.
    """
    write_tree(tmp_path, {
        MARKER_NAME: "",                                   # the ancestor
        f"project/{LEGACY_MARKER_NAME}": "",               # the project itself
    })
    assert default_t_dir(tmp_path / "project") == (tmp_path / "project").resolve()


def test_within_one_directory_the_neutral_spelling_wins(tmp_path, write_tree):
    # A project mid-migration may carry both; the new one is authoritative.
    write_tree(tmp_path, {
        MARKER_NAME: "theories-new\n",
        LEGACY_MARKER_NAME: "theories-old\n",
    })
    assert default_t_dir(tmp_path) == (tmp_path / "theories-new").resolve()


def test_an_empty_marker_means_my_own_directory(tmp_path, write_tree):
    write_tree(tmp_path, {MARKER_NAME: ""})
    assert default_t_dir(tmp_path) == tmp_path.resolve()


def test_a_marker_of_only_comments_means_my_own_directory(tmp_path, write_tree):
    write_tree(tmp_path, {MARKER_NAME: "# where the theories live\n#\n"})
    assert default_t_dir(tmp_path) == tmp_path.resolve()


def test_a_relative_path_is_resolved_against_the_marker(tmp_path, write_tree):
    # Not against the cwd: the marker is committed, and the caller's working
    # directory is not a property of the project.
    write_tree(tmp_path, {"proj/" + MARKER_NAME: "# comment\n\nt\n"})
    start = tmp_path / "proj" / "deep"
    start.mkdir()
    assert default_t_dir(start) == (tmp_path / "proj" / "t").resolve()


def test_a_marker_outranks_a_nearer_root_file(tmp_path, write_tree):
    # A ROOT is evidence; a marker is a statement.  The statement wins.
    write_tree(tmp_path, {MARKER_NAME: "t\n", "sub/ROOT": "session S\n"})
    assert default_t_dir(tmp_path / "sub") == (tmp_path / "t").resolve()


# ------------------------------------------------------------- the fallbacks

def test_the_nearest_root_file_is_used_when_no_marker_exists(tmp_path, write_tree):
    write_tree(tmp_path, {"proj/ROOT": "session S = HOL\n"})
    start = tmp_path / "proj" / "deep"
    start.mkdir()
    assert default_t_dir(start) == (tmp_path / "proj").resolve()


def test_start_itself_when_there_is_nothing_to_find(tmp_path):
    # Not an error: theories are then discovered by scanning beneath it.
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    assert default_t_dir(lonely) == lonely.resolve()
