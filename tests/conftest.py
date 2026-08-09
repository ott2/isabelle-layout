"""Shared fixtures for the isabelle-layout suite.

Deliberately thin, and deliberately *not* a `sys.path` shim.  The suite these
tests came from (`isabelle-query`'s) imports a `support.py` whose side effect
is putting `src/` on `sys.path`, so the tests run against the working tree
without an install.  That is convenient and it hides things: two
`isabelle-watchdog` failures showed up only under a real `pip install .`,
because a source tree answers questions about packaging that an installed
wheel answers differently -- what is importable, what package data exists,
what the package is even called.

This package's whole premise is being installable by other people.  So the
install path is the one under test:

    python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
    .venv/bin/python -m pytest
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def write_tree():
    """Materialise a tree from ``{relative_path: contents}``; dirs implied.

    Returns the function rather than a tree, so one test can build several.
    """
    def _write(base: Path, files: dict) -> Path:
        for rel, content in files.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return base
    return _write
