# isabelle-layout — project brief

Build a Python package that answers one question: **what structure does this
Isabelle project have, according to its own files?** Sessions, theory headers,
project roots — read from `ROOT` files and `.thy` headers, with no Isabelle
process involved.

It exists because that code already exists, in the wrong place. It is
`src/isabelle_query/common.py` in `~/projects/query` — 1,015 lines out of an
11,215-line package. Every consumer that wants a ROOT parser today installs a
*querying tool* to get one, along with its release cadence and its userbase's
compatibility constraints. This is a distribution problem, not a code problem:
the library is good, the door is wrong.

## Start by moving, not rewriting

`~/projects/query/src/isabelle_query/common.py` is the source. It has a real
tokenizer — nesting block comments, cartouches, `SessionInfo`, parent-chain
resolution — and it is correct in places a regex is not. Treat it as the
reference implementation, not a first draft.

The first commit should be a **behaviour-preserving move**: the same functions,
the same results, under a new name. Improvements come after, as separate
commits with tests that show the change. A rewrite would throw away years of
encounters with real ROOT files and you would rediscover them one by one.

## What to take

Grouped by cohesion, with line numbers in the current `common.py`:

**Project location** (~70 lines) — `MARKER_NAME` (103), `_read_marker` (106),
`default_t_dir` (131).

**ROOT parsing** (~350 lines) — `_is_terminator` (209), `parse_root_theories`
(223), `parse_root_directories` (252), `SessionInfo` (423), the comment and
cartouche machinery (465–542), `_tokenize_root` (550), `parse_root_sessions`
(598), `discover_roots` (872), `iter_sessions` (943).

**Theory headers** (~150 lines) — `resolve_thy_file` (291), `_THY_HEADER_RE`
(332), `parse_thy_imports` (338), `iter_thy_files` (373),
`resolve_session_theory` (694), `session_theories` (812).

**Structural derivation** — `resolve_base_logic` (955). Follows a session's
parent chain to its root. Derived purely from what ROOTs declare, so it is
structure, not opinion.

## What to leave behind

- **`run_guarded` (175).** Not Isabelle-specific at all, already marked
  deprecated in `common.py`, and already copied into
  `isabelle_watchdog/guard.py`. Six lines. Do not give it a third home.
- **`classify_import` (752) and `_INFRA_ROOTS` (736).** These encode an
  *analysis judgement* — what counts as infrastructure — rather than what a
  file says. Decisive evidence: no consumer outside `query` imports them.
- **`is_hol_base` (975), `is_known_nonhol_base` (1002),
  `_NONHOL_DISTRIBUTION_BASES` (998).** Borderline. They are facts about the
  Isabelle distribution rather than about the project being read, and their
  only importers are AFP-census scripts. Decide deliberately; if they come,
  they belong in a clearly separate module, because a hardcoded set of
  distribution session names ages differently from a parser.

## Let the consumers define the public API

Twelve scripts import from `common` today, across two repositories. What they
actually ask for, by frequency:

    iter_sessions            8    default_t_dir            4
    resolve_session_theory   4    iter_thy_files           4
    parse_root_sessions      3    session_theories         2
    is_hol_base              2    resolve_base_logic       2
    discover_roots           1

That list is the public surface. Everything else can stay private and stay
changeable. The current problem is precisely that `common` is a
private-sounding name doing public work, so every import feels like reaching
into internals — do not reproduce it by exporting the whole module.

Consumers are in `~/projects/claudecode/ndtht/bin/` (11 scripts) and
`~/projects/claudecode/query-private/bin/`.

## Three decisions to make before the first release

**1. The marker name.** `default_t_dir` reads `.isabelle-query`. In a neutral
package a marker named after one consumer is a wart that hardens fast, and
both `~/projects/43sp` and `~/projects/claudecode/ndtht` already have the file
committed. Either commit to it as the historical name and document why, or
introduce a neutral one and read both for a version or two. Decide before
files multiply on disk, not after.

**2. Is `SessionInfo` public?** Four of the nine most-used functions return or
take it. If it is public it is a compatibility surface forever, so decide what
is guaranteed about it — field names, or just attribute access.

**3. What is a "project root"?** `default_t_dir` walks upward unboundedly.
That suits a query tool; it does not suit every caller. `isabelle-watchdog`
deliberately bounds the equivalent search at the git top level, because
projects nest (`~/projects/claudecode/ndtht`) and overshooting there would
pool two repositories' data. Consider making the bound a parameter rather than
a policy, and let callers state which they want.

## A conformance corpus is a first-class deliverable

Ship a data file of ROOT and `.thy` snippets with their expected parses, as
**package data**, not just as tests.

This is what lets a consumer that cannot take a runtime dependency still
guarantee agreement. `isabelle-watchdog` is exactly that case: it runs beside
a build, so an unimportable dependency means an unsupervised, unrecorded
attempt — the one outcome its whole design exists to prevent. It will keep its
own 15-line parser in `roots.py` and depend on this package **as a test
dependency**, asserting agreement in CI. That arrangement only works if the
fixture is a shipped artefact.

Eight cases to seed it with, already verified against `parse_root_sessions`
and already the contents of `isabelle_watchdog/tests/test_roots.py`:

    session Probe = HOL +                        -> ["Probe"]
    session "Probe (AFP)" = HOL +                -> ["Probe (AFP)"]
    session With.Dots-2 = HOL +                  -> ["With.Dots-2"]
    session Probe in sub = HOL +                 -> ["Probe"]
    (* session Retired = HOL + *)\nsession Live  -> ["Live"]
    (*\nsession Old = HOL +\n*)\nsession Live    -> ["Live"]
    session P = HOL +\n description \<open>session Ghost = X\<close>  -> ["P"]
    session A = HOL +\n\nsession B = A +         -> ["A", "B"]

Those eight found two real defects in a hand-rolled parser: a quoted name
truncated at its first space, and a bare one at its first `.` or `-`. Grow the
table from real ROOTs — the Isabelle distribution and the AFP are the obvious
sources, and `query-private/bin/afp_census.py` already knows how to walk them.

## Migration: no flag day

Eleven `ndtht/bin` scripts import `isabelle_query.common` directly. Have
`query` depend on this package and re-export from `common` for a deprecation
window, so nothing breaks on the day of the split. Move consumers over
individually, afterwards, at whatever pace suits.

## Packaging

Mirror `~/projects/watchdog` (`isabelle-watchdog`), which is set up the way
this should be: hatchling, src-layout, version single-sourced from
`__init__.py`, `[project.optional-dependencies] test`, pytest with
`--strict-markers`, `docs/` in the sdist.

**No runtime dependencies.** `common.py` has none today and neither does
`query` itself; a parsing library that pulls in a tree is one that consumers
route around. This is also what makes the package adoptable by tools with hard
constraints of their own.

Test against a real install (`pip install .` into a fresh venv), not
`PYTHONPATH=src`. Two failures in the watchdog showed up only that way.

## Definition of done, for the first release

1. The listed functions moved, behaviour-preserving, with `query`'s existing
   tests for them moved too and passing.
2. Public API named and documented; everything else private.
3. The three decisions above made and written down, with reasons.
4. Conformance corpus shipped as package data, seeded with the eight cases and
   extended from real ROOTs.
5. `query` depends on it and re-exports from `common`; `query`'s own test
   suite passes unchanged.
6. A `README` that answers "why is this not part of isabelle-query" in a
   paragraph, because that is the first question anyone will ask.

## What not to do

- Do not rewrite the tokenizer. It is correct about nesting comments and
  cartouches in ways that are easy to get wrong and hard to notice.
- Do not move `run_guarded`.
- Do not export everything "for now". The current situation is what that
  produces.
- Do not break the eleven consumers on day one.
