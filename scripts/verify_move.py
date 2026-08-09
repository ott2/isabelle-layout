#!/usr/bin/env python3
"""Prove the move from `isabelle_query.common` was behaviour-preserving.

Not a test, and deliberately not shipped as one: it needs both packages
importable *and* a real corpus on disk, and its whole purpose is to be run
once, at the moment of the split, against the largest body of real ROOT and
`.thy` files available.  What it produces belongs in a commit message, not in
a suite that would skip itself on every machine that lacks an AFP checkout.

The argument it makes: for every function moved, and for every input the AFP
and the Isabelle distribution can supply, the old implementation and the new
one return the same thing.  A test suite says the new code is right about the
cases someone thought of; this says it is *identical* on 962 entries' worth of
cases nobody thought of.

    ~/projects/query/.venv/bin/python scripts/verify_move.py ~/repos/afp/thys

Exit 0 iff nothing disagreed.

**This script expires, and says so rather than lying.**  Once `isabelle-query`
depends on this package, `isabelle_query.common` re-exports it, and the two
"implementations" are the same function objects -- so the comparison passes
vacuously and reports 0 disagreements over 68362 checks that all compared a
function with itself.  A verification tool that cannot fail is worse than none,
because the number it prints looks exactly like the real one.  So it checks
first and refuses.  To reproduce the original run, check `isabelle-query` out
at its last pre-split commit:

    git -C ~/projects/query stash
    git -C ~/projects/query checkout 4d8b4dc -- src/isabelle_query/common.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from isabelle_query import common as old            # noqa: E402
import isabelle_layout as new                       # noqa: E402
from isabelle_layout import _lexer, distribution, roots, theories  # noqa: E402


class Report:
    """Counts of agreements, and the first few disagreements in full."""

    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []

    def same(self, what: str, a, b) -> None:
        self.checks += 1
        if a != b:
            if len(self.failures) < 20:
                self.failures.append(f"{what}\n    old: {a!r}\n    new: {b!r}")


def as_tuple(s) -> tuple:
    """A SessionInfo's contents, comparable across the two classes.

    The dataclasses are distinct types, so `==` is False even when every field
    matches; field-wise comparison is the question actually being asked.
    """
    return (s.name, s.root_path, s.in_subdir, s.parent,
            s.used_sessions, s.directories, s.theories, s.session_dir)


def refuse_if_self_comparing() -> bool:
    """True if `isabelle_query.common` is now a re-export of this package.

    Identity, not equality: after the split the two names bind the *same*
    function object, and every comparison below would then be `f(x) == f(x)`.
    """
    return old.parse_root_sessions is new.parse_root_sessions


def main(argv: list[str]) -> int:
    if refuse_if_self_comparing():
        print("REFUSING: `isabelle_query.common` now re-exports isabelle_layout,\n"
              "so this would compare every function with itself and report 0\n"
              "disagreements without checking anything.  See the module docstring\n"
              "for how to check out a pre-split `common.py`.")
        return 2
    corpora = [Path(p).expanduser() for p in argv[1:]] or \
        [Path("~/repos/afp/thys").expanduser()]
    r = Report()

    for corpus in corpora:
        if not corpus.is_dir():
            print(f"skipping {corpus} (not a directory)")
            continue
        print(f"== {corpus}")

        # --- discover_roots / iter_sessions ---------------------------------
        old_roots = old.discover_roots(corpus)
        new_roots = new.discover_roots(corpus)
        r.same(f"discover_roots({corpus})", old_roots, new_roots)
        print(f"   {len(new_roots)} ROOT files")

        old_sessions = old.iter_sessions(corpus)
        new_sessions = new.iter_sessions(corpus)
        r.same("iter_sessions len", len(old_sessions), len(new_sessions))
        for a, b in zip(old_sessions, new_sessions):
            r.same(f"iter_sessions {a.name}", as_tuple(a), as_tuple(b))
        print(f"   {len(new_sessions)} sessions")

        # --- per-ROOT parsing ----------------------------------------------
        for root in new_roots:
            text = root.read_text(errors="replace")
            r.same(f"strip_block_comments {root}",
                   old._strip_block_comments(text),
                   _lexer.strip_block_comments(text))
            r.same(f"strip_cartouches {root}",
                   old._strip_cartouches(text), _lexer.strip_cartouches(text))
            r.same(f"strip_comments {root}",
                   old._strip_comments(text), _lexer.strip_comments(text))
            r.same(f"tokenize_root {root}",
                   list(old._tokenize_root(text)),
                   list(roots._tokenize_root(text)))
            r.same(f"parse_root_sessions {root}",
                   [as_tuple(s) for s in old.parse_root_sessions(root)],
                   [as_tuple(s) for s in roots.parse_root_sessions(root)])
            # The line-oriented single-ROOT parsers, now private.
            r.same(f"parse_root_theories {root}",
                   old.parse_root_theories(root), roots._parse_root_theories(root))
            r.same(f"parse_root_directories {root}",
                   old.parse_root_directories(root),
                   roots._parse_root_directories(root))
            r.same(f"iter_thy_files {root.parent}",
                   old.iter_thy_files(root.parent),
                   theories.iter_thy_files(root.parent))

        # --- per-session resolution and closure -----------------------------
        for a, b in zip(old_sessions, new_sessions):
            for entry in a.theories:
                r.same(f"resolve_session_theory {a.name}:{entry}",
                       old.resolve_session_theory(a, entry),
                       roots.resolve_session_theory(b, entry))
            r.same(f"session_theories {a.name}",
                   old.session_theories(a), theories.session_theories(b))
            r.same(f"session_theories(no follow) {a.name}",
                   old.session_theories(a, follow_imports=False),
                   theories.session_theories(b, follow_imports=False))

        # --- every theory header in the corpus ------------------------------
        n_thy = 0
        for thy in sorted(corpus.rglob("*.thy")):
            n_thy += 1
            r.same(f"parse_thy_imports {thy}",
                   old.parse_thy_imports(thy), theories.parse_thy_imports(thy))
            text = thy.read_text(encoding="utf-8", errors="replace")
            r.same(f"strip_comments {thy}",
                   old._strip_comments(text), _lexer.strip_comments(text))
        print(f"   {n_thy} theory files")

        # --- import classification (private, but it drives the closure) -----
        for a, b in zip(old_sessions, new_sessions):
            for _name, path in theories.session_theories(b):
                for imp in theories.parse_thy_imports(path):
                    r.same(f"classify_import {a.name}:{imp}",
                           old.classify_import(imp, a, None, path),
                           theories._classify_import(imp, b, None, path))

        # --- base-logic resolution over the whole corpus --------------------
        parents = {s.name: (s.parent or "") for s in new_sessions}
        for name in parents:
            base_old = old.resolve_base_logic(name, parents)
            base_new = new.resolve_base_logic(name, parents)
            r.same(f"resolve_base_logic {name}", base_old, base_new)
            r.same(f"is_hol_base {base_old}",
                   old.is_hol_base(base_old), distribution.is_hol_base(base_new))
            r.same(f"is_known_nonhol_base {base_old}",
                   old.is_known_nonhol_base(base_old),
                   distribution.is_known_nonhol_base(base_new))

    print(f"\n{r.checks} comparisons, {len(r.failures)} disagreements")
    for f in r.failures:
        print("  " + f)
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
