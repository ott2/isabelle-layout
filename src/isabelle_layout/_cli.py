r"""_cli.py — the demonstration command, and the completeness test for the API.

A library with ten public functions and no runnable use of them is a library
whose surface has only ever been checked against itself.  `README.md` has
snippets and the probes exercise three functions, which leaves most of the
surface unexercised by anything a consumer would recognise as use.
This module is the missing thing: one program that uses the API the way
a consumer would, which doubles as a smoke test that an *installed wheel*
works — the question the test suite deliberately cannot answer from inside the
repository.

The design rule is completeness  [demo-cli]
-------------------------------------------

**Every public name appears here.**  That is a crisp criterion, and it tests
the API rather than the implementation: if the command could not be written
without reaching for a private import, the public surface would be wrong and
that would be the finding.  It is also why two flags exist that a hand-designed
tool might not have grown — see ``--roots`` and ``--files`` below.

What it found, recorded because it is the point of doing this:
:func:`~isabelle_layout.theories.iter_thy_files` is the weakest-justified name
on the surface.  It predates :func:`~isabelle_layout.roots.iter_sessions` plus
:func:`~isabelle_layout.theories.session_theories`, which subsume it for every
purpose except the one ``--files`` uses it for — the *declared* theories, in
ROOT order, deduplicated across sessions, with no import closure.  That is a
real thing to want (they are a session's entry points, the roots of its import
graph) but it is a narrow one, and if a 0.2 ever reconsiders the surface, this
is the name to reconsider.

Why a console script rather than ``python -m``  [demo-cli]
----------------------------------------------------------

The tension is real and was weighed rather than defaulted.  A
``[project.scripts]`` entry claims a name on ``PATH`` and creates a second
public surface — flags, output format, exit codes — versioned forever, and it
is the strongest possible invitation for a library with no opinions to grow
into a tool with many.  The failure mode is becoming ``isabelle-query``-lite,
at which point the split that created this package was pointless.

It ships anyway, because a second use case turned up that ``python -m`` serves
badly: an LLM orienting itself in a repository that contains Isabelle proofs as
*ancillary* artefacts, needing to know in one command what is there.  That
reader discovers a command on ``PATH``; it does not discover an import path.

What bounds the surface is the rule above rather than restraint.  Every flag
here exists to reach a public function, so the command cannot grow without the
library growing first, and "would this need a new public function?" is a
question with an answer.  Nothing here parses proof bodies, builds a call
graph, counts entries, or emits a format other than plain text; those are
``isabelle-query``'s job and it does them well.  A flag that needed ``.thy``
*bodies* rather than headers is out of scope by construction.

Cost, which shapes the default  [demo-cli]
------------------------------------------

The import closure is the expensive part by about **70×**: over the AFP,
``iter_sessions`` takes 0.31s for 988 sessions and ``session_theories`` about
7s, against ~0.1s with ``follow_imports=False``.  So ``--list`` — the "what is
here" inventory — never computes it, the detailed default does, and output is
streamed per session rather than collected, so a large corpus prints as it goes
instead of after.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import (
    SessionInfo,
    __version__,
    conformance,
    default_t_dir,
    discover_roots,
    iter_sessions,
    iter_thy_files,
    parse_root_sessions,
    parse_thy_imports,
    resolve_base_logic,
    resolve_session_theory,
    session_theories,
)
from .distribution import is_hol_base, is_known_nonhol_base

_LABEL_WIDTH = 13


def _rel(path: Path, base: Path) -> str:
    """``path`` written relative to ``base`` when it is beneath it.

    Absolute paths are correct but unreadable in bulk, and a caller who asked
    about a directory already knows where it is.
    """
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _field(label: str, value: str) -> str:
    return f"  {label:<{_LABEL_WIDTH}}{value}"


def _base_logic_note(base: str) -> str:
    """``base``, annotated with which of the two distribution predicates claims it.

    All three outcomes are shown, because the third one is the reason there are
    two predicates rather than one.  They are not each other's negation:
    :func:`is_hol_base` demands positive HOL evidence and
    :func:`is_known_nonhol_base` demands positive non-HOL evidence, so a base
    that is neither — typically a parent *session* outside the scanned scope —
    is reported as unrecognised instead of being silently sorted into whichever
    bucket a single predicate would have chosen.
    """
    if is_hol_base(base):
        return f"{base}  (HOL family)"
    if is_known_nonhol_base(base):
        return f"{base}  (a non-HOL distribution logic)"
    return (f"{base}  (not a distribution logic; the parent chain probably "
            f"leaves the scanned directory)")


def _load(target: Path) -> "tuple[Path, list[SessionInfo]]":
    """``(directory, sessions)`` for a path that may be a ROOT file or a tree.

    Both entry points are public and they answer different questions, so which
    one runs is decided by what the user pointed at rather than by a flag.
    """
    if target.is_file():
        return target.parent, parse_root_sessions(target)
    return target, iter_sessions(target)


def _declared(session: SessionInfo) -> "list[tuple[str, Path | None]]":
    """Each ROOT-declared theory paired with the file it resolves to.

    ``None`` means the ROOT names a theory with no file on disk.  Reporting
    that is worth the line it costs: it is a broken ROOT, and the failure is
    otherwise silent — the session simply builds less than it claims.
    """
    return [(entry[0], resolve_session_theory(session, entry))
            for entry in session.theories]


def _emit_session(session: SessionInfo, *, base_dir: Path,
                  parents: "dict[str, str]", closure: bool, verbose: bool,
                  out) -> None:
    print(session.name, file=out)
    print(_field("root", _rel(session.root_path, base_dir)), file=out)
    if session.in_subdir:
        print(_field("in", session.in_subdir), file=out)
    if session.parent:
        print(_field("parent", session.parent), file=out)
        print(_field("base logic",
                     _base_logic_note(resolve_base_logic(session.name, parents))),
              file=out)
    if session.used_sessions:
        print(_field("uses", ", ".join(session.used_sessions)), file=out)
    if session.directories:
        print(_field("directories", ", ".join(session.directories)), file=out)

    declared = _declared(session)
    missing = [name for name, path in declared if path is None]
    summary = f"{len(declared)} theor{'y' if len(declared) == 1 else 'ies'}"
    if declared:
        summary += "   " + ", ".join(name for name, _p in declared)
    if missing:
        summary += f"   [no file on disk: {', '.join(missing)}]"
    print(_field("declared", summary), file=out)

    if closure:
        built = session_theories(session)
        print(_field("builds", f"{len(built)} theories"), file=out)
        if verbose:
            print("  theories", file=out)
            for name, path in built:
                print(f"    {name:<28} {_rel(path, session.session_dir)}",
                      file=out)
                imports = parse_thy_imports(path)
                if imports:
                    print(f"      imports  {'  '.join(imports)}", file=out)


def _emit_list(sessions: "list[SessionInfo]", base_dir: Path, out) -> None:
    """One line per session, no import closure — the cheap inventory."""
    # The header is part of the column, or a corpus of short names prints a
    # table whose heading does not line up with its own rows.
    width = max([len(s.name) for s in sessions] + [len("SESSION")])
    pwidth = max([len(s.parent or "-") for s in sessions] + [len("PARENT")])
    print(f"{'SESSION':<{width}}  {'PARENT':<{pwidth}}  DECL  ROOT", file=out)
    for s in sessions:
        print(f"{s.name:<{width}}  {s.parent or '-':<{pwidth}}  "
              f"{len(s.theories):>4}  {_rel(s.root_path, base_dir)}", file=out)


def _self_check(out) -> int:
    """Check this build against the conformance corpus shipped beside it.

    Deliberately end-to-end: the corpus is read through
    :mod:`isabelle_layout.conformance`, so on an installed wheel this verifies
    that the package *data* is present and readable, which importing the code
    alone does not.
    """
    corpus = conformance.load()
    cases = conformance.cases(accepted_only=True)
    print(f"conformance corpus: {len(conformance.cases())} cases "
          f"({len(cases)} accepted), verified against "
          f"{corpus['verified_against']}", file=out)

    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ROOT"
        for case in cases:
            root.write_text(case["root"], encoding="utf-8")
            got = [s.name for s in parse_root_sessions(root)]
            want = conformance.session_names(case)
            if got != want:
                bad.append((case["id"], want, got))

    if not bad:
        print(f"  {len(cases)}/{len(cases)} agree", file=out)
        return 0
    print(f"  {len(bad)} of {len(cases)} DISAGREE:", file=out)
    for case_id, want, got in bad:
        print(f"    {case_id}: expected {want}, got {got}", file=out)
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="isabelle-layout",
        description="What structure does this Isabelle project have, "
                    "according to its own files? Reads ROOT files and .thy "
                    "headers; starts no prover and needs no built heap.",
        epilog="Exit status: 0 found something, 1 found nothing (or "
               "--self-check disagreed), 2 bad usage.")
    p.add_argument("path", nargs="?", metavar="PATH",
                   help="a directory to scan, or a single ROOT file. "
                        "Default: the project root, found via "
                        "$ISABELLE_LAYOUT_ROOT, a .isabelle-layout marker, or "
                        "the nearest directory holding a ROOT.")
    p.add_argument("-l", "--list", action="store_true",
                   help="one line per session, without the import closure. "
                        "The fast inventory: ~70x cheaper on a large corpus.")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also list every theory a session builds, with its "
                        "imports.")
    p.add_argument("--no-closure", action="store_true",
                   help="skip the import closure, so 'builds' is not "
                        "reported. What a ROOT declares is usually far less "
                        "than what it builds.")
    p.add_argument("--roots", action="store_true",
                   help="list the ROOT files found, one per line, and stop.")
    p.add_argument("--files", action="store_true",
                   help="list the declared theory files, one per line, and "
                        "stop. These are a session's entry points, not its "
                        "full import closure.")
    p.add_argument("--self-check", action="store_true",
                   help="check this installation against the conformance "
                        "corpus shipped inside it, and stop.")
    p.add_argument("-V", "--version", action="version",
                   version=f"isabelle-layout {__version__}")
    return p


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out = sys.stdout

    if args.self_check:
        return _self_check(out)

    if args.path is None:
        target = default_t_dir()
    else:
        target = Path(args.path).expanduser()
        if not target.exists():
            parser.error(f"no such file or directory: {target}")
    target = target.resolve()

    if args.roots:
        roots = discover_roots(target) if target.is_dir() else [target]
        for root in roots:
            print(root, file=out)
        return 0 if roots else 1

    if args.files:
        files = iter_thy_files(target if target.is_dir() else target.parent)
        for thy in files:
            print(thy, file=out)
        return 0 if files else 1

    base_dir, sessions = _load(target)
    if not sessions:
        print(f"{target}: no Isabelle sessions found "
              f"(no ROOT file declares one)", file=out)
        return 1

    root_count = len({s.root_path for s in sessions})
    print(f"{target} — {root_count} ROOT file"
          f"{'' if root_count == 1 else 's'}, {len(sessions)} session"
          f"{'' if len(sessions) == 1 else 's'}", file=out)
    print(file=out)

    if args.list:
        _emit_list(sessions, base_dir, out)
        return 0

    # Built once over every session in scope, because a base logic two hops up
    # (`Forcing` -> `ZF-Constructible`) resolves to the root only when the whole
    # chain is present -- the classification an immediate-parent test gets wrong.
    parents = {s.name: s.parent for s in sessions if s.parent}
    closure = not args.no_closure
    for i, session in enumerate(sessions):
        if i:
            print(file=out)
        _emit_session(session, base_dir=base_dir, parents=parents,
                      closure=closure, verbose=args.verbose, out=out)
        out.flush()  # stream: the closure makes a large corpus slow to finish
    return 0


if __name__ == "__main__":  # `python -m isabelle_layout._cli`, for development
    sys.exit(main())
