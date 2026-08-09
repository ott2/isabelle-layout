"""`discover_roots` must scope like `isabelle build -D`.

When a directory carries a `ROOTS` index, discovery follows only the
subdirectories it lists (recursing into nested `ROOTS`), so scan scope
equals build scope — a sibling session deliberately omitted from `ROOTS`
is excluded from the tool exactly as it is from the build.  Without an
index, discovery falls back to a recursive walk so single-ROOT and
ad-hoc layouts still resolve.  These tests pin both modes.

Moved from `isabelle-query`'s suite with the code they cover, and converted
from `unittest` to plain pytest against an installed package.
"""

from __future__ import annotations

from pathlib import Path

from isabelle_layout import discover_roots


def roots_under(root_dir: Path) -> list[str]:
    """ROOT files discovered under `root_dir`, as posix paths relative to it,
    sorted — convenient for asserting against a literal list."""
    base = root_dir.resolve()
    return sorted(p.relative_to(base).as_posix() for p in discover_roots(root_dir))


def test_index_limits_scope_to_listed_dirs(tmp_path, write_tree):
    # `exc` has a ROOT on disk but is omitted from ROOTS -> excluded,
    # just as `isabelle build -D` would never elaborate it.
    write_tree(tmp_path, {
        "ROOTS": "inc\n",
        "inc/ROOT": "session inc = HOL\n",
        "exc/ROOT": "session exc = HOL\n",
    })
    assert roots_under(tmp_path) == ["inc/ROOT"]


def test_index_ignores_comments_and_blank_lines(tmp_path, write_tree):
    write_tree(tmp_path, {
        "ROOTS": "# a chapter comment\n\n  inc  \n",
        "inc/ROOT": "session inc = HOL\n",
        "exc/ROOT": "session exc = HOL\n",
    })
    assert roots_under(tmp_path) == ["inc/ROOT"]


def test_index_skips_listed_but_missing_dir(tmp_path, write_tree):
    # A ROOTS entry with no directory on disk is silently ignored.
    write_tree(tmp_path, {
        "ROOTS": "inc\nghost\n",
        "inc/ROOT": "session inc = HOL\n",
    })
    assert roots_under(tmp_path) == ["inc/ROOT"]


def test_top_level_root_alongside_index_is_kept(tmp_path, write_tree):
    # AFP's `thys/` carries both a ROOTS index and a top-level ROOT (the
    # chapter-definition file); both the top ROOT and the listed entry's
    # ROOT are returned.
    write_tree(tmp_path, {
        "ROOTS": "inc\n",
        "ROOT": "chapter AFP\n",
        "inc/ROOT": "session inc = HOL\n",
    })
    assert roots_under(tmp_path) == ["ROOT", "inc/ROOT"]


def test_nested_roots_are_followed(tmp_path, write_tree):
    # A listed dir may itself carry a ROOTS index; recursion follows it
    # while still excluding siblings omitted at each level.
    write_tree(tmp_path, {
        "ROOTS": "grp\n",
        "grp/ROOT": "session grp = HOL\n",
        "grp/ROOTS": "leaf\n",
        "grp/leaf/ROOT": "session leaf = HOL\n",
        "grp/other/ROOT": "session other = HOL\n",  # omitted -> excluded
    })
    assert roots_under(tmp_path) == ["grp/ROOT", "grp/leaf/ROOT"]


def test_duplicate_index_entries_dedup(tmp_path, write_tree):
    write_tree(tmp_path, {
        "ROOTS": "inc\ninc\n",
        "inc/ROOT": "session inc = HOL\n",
    })
    assert roots_under(tmp_path) == ["inc/ROOT"]


def test_no_index_recursive_walk_skips_hidden(tmp_path, write_tree):
    # No ROOTS -> recursive fallback finds every ROOT (including nested),
    # but skips hidden directories.
    write_tree(tmp_path, {
        "one/ROOT": "session one = HOL\n",
        "two/nested/ROOT": "session two = HOL\n",
        ".hidden/ROOT": "session hidden = HOL\n",
    })
    assert roots_under(tmp_path) == ["one/ROOT", "two/nested/ROOT"]


def test_no_index_hidden_ancestor_does_not_suppress(tmp_path, write_tree):
    # root_dir living *under* a hidden directory must not cause the walk to
    # skip everything: "hidden" is judged relative to root_dir, not the
    # absolute path.  (The old full-`parts` test found nothing here.)
    write_tree(tmp_path, {
        ".cache/proj/ROOT": "session p = HOL\n",
        ".cache/proj/sub/ROOT": "session q = HOL\n",
    })
    assert roots_under(tmp_path / ".cache" / "proj") == ["ROOT", "sub/ROOT"]


def test_no_index_dotdot_in_path_not_treated_as_hidden(tmp_path, write_tree):
    # A `..` in the path as given is not a hidden component, so a relative
    # root such as `../proj` resolves normally.
    write_tree(tmp_path, {
        "ROOT": "session s = HOL\n",
        "sub/ROOT": "session t = HOL\n",
    })
    root = tmp_path / "sub" / ".."  # filesystem-equals tmp_path, but carries '..'
    assert len(discover_roots(root)) == 2


def test_missing_directory_returns_empty(tmp_path):
    assert discover_roots(tmp_path / "nope") == []
