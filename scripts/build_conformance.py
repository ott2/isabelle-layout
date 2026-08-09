#!/usr/bin/env python3
"""Regenerate the conformance corpus, verified against a real Isabelle.

The corpus is a shipped artefact, so its provenance matters more than its
convenience.  Every case here is put to `isabelle sessions -d`, which is the
same session-structure reader `isabelle build` uses, and the answer is
recorded alongside the expected parse.  That is what lets the corpus say two
different things and keep them apart:

  - **conformance** — Isabelle accepts this ROOT and declares these sessions,
    so any parser that disagrees is wrong;
  - **robustness** — Isabelle *rejects* this ROOT, so there is no ground truth
    to conform to, but readers still have to agree on what they do with it
    rather than each inventing a different silent renaming.

That distinction is not decoration.  Two of the eight cases this corpus was
seeded with are inputs `isabelle build` refuses outright, and presenting them
as "what Isabelle does" would have been false.

Usage (needs Isabelle on PATH; without it, nothing is regenerated):

    python3 scripts/build_conformance.py

Writes `src/isabelle_layout/data/conformance.json`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from isabelle_layout import parse_root_sessions  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "src/isabelle_layout/data/conformance.json"


# (id, why, root_text).  `why` is the case's reason for existing; a case that
# cannot say what it would catch is a case nobody will maintain.
CASES: list[tuple[str, str, str]] = [
    # ---------------------------------------------------------- the basics
    ("plain",
     "The simplest declaration there is. If this fails nothing else matters.",
     "session Probe = HOL +\n  theories\n    X\n"),
    ("quoted-name",
     "288 of 979 real ROOTs quote the session name. The quotes are not part "
     "of it.",
     'session "MHComputation" = HOL +\n'),
    ("quoted-name-with-dots-and-hyphens",
     "A quoted name may contain `.` and `-`, and Isabelle session names "
     "routinely do (`HOL-Analysis`). Truncating at either renames the session "
     "to one that exists, which is the worst kind of wrong answer. This is the "
     "valid spelling of the defect found in a hand-rolled parser.",
     'session "With.Dots-2" = HOL +\n'),
    ("groups-in-parens",
     "`(slow very_slow)` are build groups, not part of the name; 90 real ROOTs "
     "carry them. The group names must not leak into the token stream either.",
     'session Probe (slow very_slow) = HOL +\n'),
    ("in-clause",
     "`in <dir>` says where the theories live, and is not part of the name. "
     "29 real ROOTs use it.",
     "session Probe in sub = HOL +\n"),
    ("qualified-parent",
     "The parent is a session name in its own right and may be qualified.",
     'session Probe = "HOL-Library" +\n'),
    ("two-sessions-one-root",
     "One ROOT may declare many; 37 real ROOTs do, and HOL/ROOT declares "
     "dozens. A reader that stops at the first is wrong about most of them.",
     "session A = HOL +\n\nsession B in sub = A +\n"),
    ("chapter-then-session",
     "975 of 979 real ROOTs open with `chapter AFP`. It declares no session.",
     "chapter AFP\n\nsession Probe = HOL +\n"),

    # ------------------------------------------------------------- clauses
    ("sessions-clause",
     "`sessions` names cross-session dependencies without heap inheritance. "
     "550 real ROOTs have one; its entries are not sessions being declared. "
     "Both entries name real distribution sessions, because `isabelle "
     "sessions` resolves them and would reject an invented one — a semantic "
     "complaint, not a syntactic one, and not what this case is about.",
     'session Probe = HOL +\n  sessions\n    "HOL-Library"\n    "HOL-Algebra"\n'),
    ("directories-clause",
     "`directories` adds search paths for theory files. 138 real ROOTs use it.",
     'session Probe = HOL +\n  directories "sub" "other"\n'
     '  theories\n    Deep\n'),
    ("theories-block-options",
     "`theories [document = false]` — block options belong to the block, not "
     "to a theory. 134 real ROOTs write this, and `document` is not a theory.",
     "session Probe = HOL +\n  theories [document = false]\n    X\n    Y\n"),
    ("path-valued-theory-name",
     "How Isabelle addresses a theory in a subdirectory — there is no "
     "per-theory `in` clause. 127 real ROOTs do this.",
     'session Probe = HOL +\n  theories\n    "example/Example"\n'),
    ("theory-global-annotation",
     "`(global)` marks a theory as globally visible. 13 real ROOTs use it, and "
     "`global` is an annotation rather than a second theory.",
     'session Probe = HOL +\n  theories\n    X (global)\n'),
    ("document-files",
     "969 of 979 real ROOTs end with one. Its arguments are file names, not "
     "theories.",
     'session Probe = HOL +\n  theories\n    X\n'
     '  document_files\n    "root.tex"\n'),

    # ------------------------------------------------------------ comments
    ("comment-one-line",
     "A commented-out session declares nothing.",
     "(* session Retired = HOL + *)\nsession Live = HOL +\n"),
    ("comment-across-lines",
     "The same, spanning lines, which a line-oriented reader cannot see: it "
     "has no state carrying `we are inside a comment` from one line to the "
     "next, so the declaration looks live.",
     "(*\nsession Old = HOL +\n*)\nsession Live = HOL +\n"),
    ("nested-comment",
     "Isabelle's block comments NEST. A non-greedy `(*.*?*)` closes at the "
     "first `*)` and re-exposes the tail of the outer comment, resurrecting "
     "exactly the declaration that was commented out.",
     "(* outer (* inner *)\nsession Ghost = HOL +\n*)\nsession Live = HOL +\n"),
    ("description-cartouche",
     "A `description` cartouche is free text and may contain anything, "
     "including the word `session` at the start of a line.",
     "session Probe = HOL +\n"
     "  description \\<open>session Ghost = X\\<close>\n"),
    ("comment-inside-theories-block",
     "15 real ROOTs write the word `in` inside a `theories` stanza; every one "
     "of them is in a comment like this.",
     "session Probe = HOL +\n  theories\n"
     "    (* Basic helpers (in util folder) *)\n    X\n"),

    # ---------------------------------------- no sessions at all
    ("chapter-definition-only",
     "AFP's own `thys/ROOT` is exactly this. It declares no session, and that "
     "is not an error — a reader that treats an empty result as a failure "
     "reports a broken corpus for a well-formed one.",
     "chapter_definition AFP\n"),
    ("empty",
     "An empty ROOT declares nothing, and must do so by returning an empty "
     "list rather than raising. Callers walk trees full of files they did not "
     "write, and a reader that throws on one of them cannot finish the walk.",
     ""),

    # ------------------------- inputs Isabelle rejects: robustness, not truth
    ("quoted-name-with-spaces",
     "Isabelle REJECTS this — a session name may not contain spaces or parens. "
     "Kept because readers must still agree on what they do with it: the "
     "hand-rolled parser truncated at the first space and recorded a build of "
     "`Probe (AFP)` against a session named `Probe`, with nothing downstream "
     "able to tell. Agreement on malformed input is what stops one reader "
     "silently renaming what another built.",
     'session "Probe (AFP)" = HOL +\n'),
    ("bare-name-with-dots-and-hyphens",
     "Isabelle REJECTS this — `-` is a symbolic identifier, so a bare name "
     "cannot contain one; the quoted form above is the legal spelling. Kept "
     "for the same reason: the hand-rolled parser truncated it at the first "
     "`.` or `-`, turning it into a different, existing session.",
     "session With.Dots-2 = HOL +\n"),
    ("unterminated-comment",
     "An unterminated `(*` swallows the rest of the file, which is what "
     "Isabelle's lexer does. Guessing otherwise would mean a typo yields a "
     "session list nobody can build.",
     "session A = HOL +\n(* oops\nsession B in sub = A +\n"),
    ("two-sessions-sharing-a-directory",
     "Parses cleanly and still will not build: two sessions in one directory "
     "is a semantic error, not a syntactic one, so `isabelle sessions` rejects "
     "a ROOT whose session list this package reads correctly. Kept because it "
     "is the distinction the `isabelle` field would otherwise blur — "
     "`rejects` means `isabelle build` refuses the file, NOT that a reader "
     "which parsed it got the wrong answer. Adding `in sub` to the second "
     "declaration is the buildable form, covered above.",
     "session A = HOL +\n\nsession B = A +\n"),
]


def ask_isabelle(root_text: str) -> tuple[str, list[str], str]:
    """(verdict, sessions, note) from `isabelle sessions -d` on this ROOT."""
    if not shutil.which("isabelle"):
        return ("unknown", [], "no isabelle on PATH")
    baseline = _sessions_of(None)
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "ROOT").write_text(root_text)
        (Path(d) / "sub").mkdir()
        out = _run(["isabelle", "sessions", "-d", d, "-a"])
        # The temporary directory's name is in every diagnostic and changes on
        # every run.  Left in, the corpus would show a diff each time it was
        # regenerated, which trains everyone to stop reading those diffs.
        # Resolved form first: on macOS `/var/...` is a symlink to
        # `/private/var/...`, and Isabelle prints the resolved path.  Replacing
        # the unresolved one first leaves a `/private<ROOT-DIR>` stub behind.
        out = out.replace(str(Path(d).resolve()), "<ROOT-DIR>").replace(
            d, "<ROOT-DIR>")
    if out.startswith("***") or "\n***" in out:
        note = " ".join(ln.strip("* ").strip()
                        for ln in out.splitlines() if ln.startswith("***"))
        return ("rejects", [], " ".join(note.split())[:300])
    found = [s for s in out.split() if s and s not in baseline]
    return ("accepts", found, "")


_BASELINE: list[str] = []


def _sessions_of(_ignored) -> set:
    if not _BASELINE:
        _BASELINE.extend(_run(["isabelle", "sessions", "-a"]).split())
    return set(_BASELINE)


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stdout or "") + (p.stderr or "")


def parse_with_this_package(root_text: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "ROOT"
        root.write_text(root_text)
        return [
            {
                "name": s.name,
                "parent": s.parent,
                "in_subdir": s.in_subdir,
                "used_sessions": list(s.used_sessions),
                "directories": list(s.directories),
                "theories": [[n, o] for n, o in s.theories],
            }
            for s in parse_root_sessions(root)
        ]


def main() -> int:
    isabelle_version = _run(["isabelle", "version"]).strip() or "unknown"
    cases = []
    disagreements = 0
    for case_id, why, root_text in CASES:
        verdict, isa_sessions, note = ask_isabelle(root_text)
        expect = parse_with_this_package(root_text)
        names = [s["name"] for s in expect]
        entry = {
            "id": case_id,
            "why": why,
            "root": root_text,
            "isabelle": verdict,
            "expect": expect,
        }
        if note:
            entry["isabelle_note"] = note
        cases.append(entry)
        if verdict == "accepts" and sorted(names) != sorted(isa_sessions):
            disagreements += 1
            print(f"  DISAGREEMENT {case_id}: isabelle={isa_sessions} "
                  f"parsed={names}")
        print(f"  {verdict:8s} {case_id:34s} -> {names}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema": 1,
        "verified_against": isabelle_version,
        "cases": cases,
    }, indent=2, ensure_ascii=False) + "\n")
    accepted = sum(1 for c in cases if c["isabelle"] == "accepts")
    print(f"\n{len(cases)} cases ({accepted} Isabelle-accepted, "
          f"{len(cases) - accepted} rejected-but-pinned), "
          f"{disagreements} disagreements -> {OUT}")
    return 1 if disagreements else 0


if __name__ == "__main__":
    sys.exit(main())
