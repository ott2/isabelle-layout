#!/usr/bin/env python3
r"""Does `session_theories` agree with `isabelle build` about what a session loads?

`scripts/probe_discovery_closure.py` checks an *invariant* — that the load set
is closed under in-entry imports.  It needs no prover, which is its virtue, and
it can only ever find holes of one shape: a closed set that is uniformly too
small, or uniformly too large, satisfies it perfectly.  This probe checks the
*value* instead, against the only authority there is.

``isabelle build -n -l`` lists the source files a session build reads.  That is
the same dependency resolution ``isabelle build`` performs, so it settles
questions that reading `sessions.scala` only half-answers — whether a
``directories`` entry may leave the ROOT's own directory (it may), whether a
bare import is looked up recursively or only in the declared directories (only
the declared ones), whether two sessions may claim one directory (they may not;
Isabelle errors).

**The two sides answer slightly different questions, and the difference is the
whole design.**  ``isabelle build -l`` lists every source the build *reads*,
including theories belonging to other sessions: `HOL` lists
`Tools/Code_Generator.thy`, which the `Tools` session owns and which `HOL.thy`
imports as ``Tools.Code_Generator``.  `session_theories` deliberately excludes
cross-entry imports, so that over a whole corpus each entry contributes its own
theories exactly once.  Comparing the raw sets therefore reports thousands of
spurious differences.

So the comparison is stated as an asymmetric invariant, which is what makes it
able to fail for the right reasons:

    over-claim   we return a file Isabelle does not read for this session
                 -> always wrong.  Must be 0.

    under-claim  Isabelle reads a file we do not return.  Acceptable exactly
                 when the file lies OUTSIDE the session's own directories,
                 because then it belongs to another session and excluding it
                 is the documented behaviour.  A miss INSIDE our own
                 directories is a hole.  Must be 0.

Measured against Isabelle2025-2:

    distribution   132 sessions   over-claim 0   inside-miss 0    (471 outside)
    AFP            988 sessions   over-claim 0   inside-miss 0  (10850 outside)

The AFP run takes about five minutes, nearly all of it inside Isabelle.

**One trap, recorded because it produced a plausible wrong answer rather than
an error.**  A block header may carry a group: ``Session HOL/HOL (main)``,
``Session Doc/Intro (doc)``.  A parser that requires the line to end at the
session name skips those headers, and every file under them is then attributed
to the *previous* session — which yields a confident report that `HOL-Lattice`
is missing 394 theories from `Doc/Codegen`.  Nothing about the output announces
that it is nonsense.

Usage:  probe_against_isabelle.py [CORPUS ...]      (default: the distribution)

Exit 0 iff no over-claim and no inside-miss.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from isabelle_layout import iter_sessions, session_theories  # noqa: E402
from isabelle_layout.theories import _theory_search_roots  # noqa: E402


# "Session CHAPTER/NAME" with an optional trailing "(group)" -- see the trap
# described above; the group is why this is not anchored at the name.
_HEADER_RE = re.compile(r"^Session ([^/]+)/(\S+)(?:\s+\(.*\))?\s*$")


def isabelle_sources(corpus: "Path | None") -> "dict[str, set[Path]]":
    """`isabelle build -n -l -a`, parsed into session -> source .thy files.

    ``-d`` is passed only for a corpus Isabelle does not already know about;
    the distribution is on its search path already, and naming it explicitly
    is an error ("Bad session root directory", since ``src`` holds neither a
    ROOT nor a ROOTS).
    """
    cmd = ["isabelle", "build", "-n", "-l", "-a"]
    if corpus is not None:
        cmd += ["-d", str(corpus)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # A nonzero exit is expected: `-n` reports sessions with no build database.
    # The listing is still emitted, so parse regardless and let the comparison
    # speak.  An empty parse is caught by the caller.
    out: "dict[str, set[Path]]" = {}
    current: "str | None" = None
    for line in proc.stdout.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            current = m.group(2)
            out[current] = set()
        elif current is not None and line.strip().endswith(".thy"):
            out[current].add(Path(line.strip()).resolve())
    if not out:
        sys.stderr.write(proc.stdout[-2000:] + proc.stderr[-2000:])
    return out


def probe(corpus: Path, oracle: "dict[str, set[Path]]") -> int:
    compared = over = outside = inside = 0
    faults: "list[str]" = []
    for session in iter_sessions(corpus):
        expected = oracle.get(session.name)
        if expected is None:
            continue  # Isabelle did not report it (excluded, or a build error)
        compared += 1
        ours = {p.resolve() for _name, p in session_theories(session)}
        roots = [r.resolve() for r in _theory_search_roots(session)]

        for p in sorted(ours - expected):
            over += 1
            faults.append(f"    OVER  [{session.name}] {p} -- not read by the build")
        for p in sorted(expected - ours):
            if any(r == p or r in p.parents for r in roots):
                inside += 1
                faults.append(f"    MISS  [{session.name}] {p} -- inside our own dirs")
            else:
                outside += 1  # another session's theory: excluded by design

    print(f"{corpus}")
    print(f"  {compared:,} sessions compared against isabelle build -l")
    print(f"  over-claim {over}   inside-miss {inside}   "
          f"({outside:,} cross-session, excluded by design)")
    if not faults:
        print("  AGREES — every difference is a cross-session theory.")
        return 0
    print(f"  {len(faults)} FAULT(S):")
    for line in faults[:40]:
        print(line)
    if len(faults) > 40:
        print(f"    ... and {len(faults) - 40} more")
    return 1


def main(argv: "list[str]") -> int:
    corpora = [Path(p).expanduser().resolve() for p in argv[1:]]
    rc = 0
    if not corpora:  # the distribution, which Isabelle already knows about
        src = subprocess.run(["isabelle", "getenv", "-b", "ISABELLE_HOME"],
                             capture_output=True, text=True).stdout.strip()
        if not src:
            print("cannot locate ISABELLE_HOME -- is isabelle on PATH?")
            return 2
        oracle = isabelle_sources(None)
        if not oracle:
            print("isabelle build produced no listing")
            return 2
        return probe(Path(src) / "src", oracle)
    for corpus in corpora:
        if not corpus.is_dir():
            print(f"skipping {corpus} (not a directory)")
            continue
        oracle = isabelle_sources(corpus)
        if not oracle:
            print(f"isabelle build produced no listing for {corpus}")
            rc = 2
            continue
        rc = probe(corpus, oracle) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
