#!/usr/bin/env python3
r"""Is the discovered load set CLOSED under in-entry imports?

`session_theories` promises to load what `isabelle build` compiles: a
session's ROOT-declared theories plus the transitive closure of their in-entry
`imports`.  That promise is checkable over a whole corpus, with no Isabelle
and no expected-output file, because it is an *invariant* rather than a value:

    if theory T is in the load set, and T imports a bare name that resolves
    to a `.thy` beside it, that file must be in the load set too.

A violation is a silent hole.  The theory is compiled by Isabelle and
invisible here, so every count is plausible and every one is short — which is
exactly how `[thy-header]`'s `%tag` bug hid: AODV's ROOT declares only `All`,
so mis-reading that one header removed 72 theories while nothing looked wrong.

This probe lives in `isabelle-layout` because the guarantee does.  It was
written in `isabelle-query`, which is where the failure was noticed, and the
fix it pointed at (`[session-dirs]`) was here — an in-entry import could not
be resolved through a `directories` entry that escaped the session directory.
A check for a promise should sit with whoever makes the promise, or it only
runs when somebody downstream happens to look.

Usage:  probe_discovery_closure.py [CORPUS ...]      (default: the AFP)

Exit 0 iff closed.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from isabelle_layout import (  # noqa: E402
    iter_sessions, parse_thy_imports, session_theories,
)


def main(argv: list[str]) -> int:
    corpora = [Path(p).expanduser() for p in argv[1:]] or \
        [Path("~/repos/afp/thys").expanduser()]
    rc = 0
    for corpus in corpora:
        if not corpus.is_dir():
            print(f"skipping {corpus} (not a directory)")
            continue

        loaded: set[Path] = set()
        reached_by: dict[Path, set] = defaultdict(set)
        sessions = 0
        for session in iter_sessions(corpus):
            sessions += 1
            for _name, path in session_theories(session):
                if path.is_file():
                    rp = path.resolve()
                    loaded.add(rp)
                    reached_by[rp].add(session.name)

        holes, checked = [], 0
        for p in sorted(loaded):
            for tok in parse_thy_imports(p):
                # A dot-qualified name addresses another session, and a name
                # resolving to no sibling file is the base library or another
                # entry -- neither is followed, by design.  What must hold is
                # the bare, resolves-beside-me case.
                if "." in tok and "/" not in tok:
                    continue
                cand = (p.parent / f"{tok}.thy").resolve()
                if not cand.is_file():
                    continue
                checked += 1
                if cand not in loaded:
                    holes.append((p, tok, cand))

        print(f"{corpus}")
        print(f"  {len(loaded):,} theories over {sessions:,} sessions; "
              f"{checked:,} in-entry imports checked")
        if not holes:
            print("  CLOSED — every in-entry import resolves into the load set.")
            continue
        rc = 1
        print(f"  {len(holes)} HOLE(S):")
        for importer, tok, missing in holes:
            who = ", ".join(sorted(reached_by.get(importer.resolve(), {"?"})))
            print(f"    [{who}] {importer.name} imports {tok!r} -> "
                  f"{missing} not loaded")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
