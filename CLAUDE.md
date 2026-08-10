# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this repository is

`isabelle-layout` answers one question: **what structure does this Isabelle
project have, according to its own files?** Sessions, theory headers, project
roots — read from `ROOT` files and `.thy` headers, with no Isabelle process
involved.

It exists because that code was in the wrong place. It was
`isabelle_query.common`, 1,015 lines inside an 11,000-line querying tool, so
every consumer who wanted a ROOT parser had to install a CLI to get one. That
is a distribution problem, not a code problem. `README.md` argues the case at
length; `isabelle-layout-prompt.md` is the original brief and the normative
statement of scope.

## Status: v0.1.0, complete and unpublished

The package is built, tested, and ready to release. Everything in the brief's
definition of done is met.

| | |
|---|---|
| Version | `0.1.0`, single-sourced in `src/isabelle_layout/__init__.py` |
| Tests | 206, passing against a real install |
| Conformance corpus | 25 cases, verified against Isabelle2025-2 |
| AFP closure | 9,910 theories / 988 sessions — `CLOSED` |
| Distribution closure | 1,824 theories / 135 sessions — `CLOSED` |
| Packaging | `twine check` passes on wheel and sdist; `py.typed` shipped |
| PyPI | name is free; **not yet published** |

**The one remaining step before publishing** is creating
`https://github.com/ott2/isabelle-layout`, which the package metadata already
points at and which currently 404s. Then:

```sh
rm -rf dist && python -m build && twine check dist/* && twine upload dist/*
```

CI was **deliberately deferred** (the user chose "publish 0.1.0 now, CI
after"). Consequence to remember: `requires-python = ">=3.9"` and the
classifiers through 3.14 are verified *statically only* — every module parses
under `ast.parse(feature_version=(3, 9))`, all carry
`from __future__ import annotations`, and there is no runtime PEP 604, no
match statement, and no post-3.9 stdlib call. Only 3.14 is installed on this
machine. A CI matrix is what would close that, and it is the first thing to
add after release.

## Architecture: the dependency direction is the design

The brief grouped the code by cohesion. The source has a dependency structure
that cuts across that grouping in one place that matters, and the module
layout follows the dependency structure instead.

```
    project.py     marker files, root discovery -- filesystem, not parsing
        |
    roots.py       SessionInfo, the ROOT tokenizer, ROOT-level API
        |
    theories.py    .thy headers, and the import closure built on them
        |
    _lexer.py      <- shared by BOTH roots and theories

    distribution.py    facts about Isabelle, not about your project
    conformance.py     the shipped corpus, and how to read it
```

**`_lexer` exists because comment-stripping is shared.** `_tokenize_root`
calls it and so does `parse_thy_imports`. Duplicating it would recreate,
inside this package, exactly the divergence the package exists to end. Do not
inline it back into either caller.

**`distribution.py` is separate on purpose.** A hardcoded list of object-logic
names ages differently from a parser: a parser breaks loudly when the grammar
moves, a name list quietly misclassifies when Isabelle adds a logic. It is
public but **not re-exported at the top level**, so the import line says which
kind of claim the caller relies on.

## The public API, and the rule that defines it

Ten names, in `__all__`, chosen by *evidence* — what consuming scripts across
two repositories actually import:

`iter_sessions`, `discover_roots`, `parse_root_sessions`,
`resolve_session_theory`, `session_theories`, `parse_thy_imports`,
`iter_thy_files`, `resolve_base_logic`, `default_t_dir`, `SessionInfo`.

Plus `isabelle_layout.distribution.{is_hol_base, is_known_nonhol_base}` and
`isabelle_layout.conformance`.

`tests/test_public_api.py` pins this. Adding a name is a deliberate act;
removing one fails loudly. The failure being avoided is `common`'s: a
private-sounding module doing public work, which nobody could change because
nobody could say what was public. **Do not export anything "for now."**

Two things are private on purpose and tests assert their absence:
`_classify_import` (deciding what counts as "infrastructure" is an analysis
judgement, not a reading of a file) and `run_guarded` (which never moved).

## Decisions

Reasoning lives in **commit messages**, indexed by `docs/decisions.md`, which
deliberately contains no reasoning of its own — only tags, so nothing can
drift. `isabelle-watchdog` keeps a CHANGELOG and `isabelle-query` keeps
neither; this package follows the latter, and `docs/decisions.md` says why.

```sh
git log --grep='\[marker-name\]'
```

| Tag | Decision |
|-----|----------|
| `[marker-name]` | `.isabelle-layout` / `$ISABELLE_LAYOUT_ROOT` primary; historical `.isabelle-query` read as an alias, permanently. Both names tested at *each level* of the walk, so proximity beats spelling. |
| `[session-info]` | `SessionInfo` is public; the field **names** and types are the contract. Not dataclass-ness, equality, ordering, `repr`, field order, or mutability. |
| `[root-bound]` | The upward search is unbounded by default and bounded by `bound=` on request. Not a git dependency — the caller computes the boundary. |
| `[session-dirs]` | Two closure holes, fixed. See `docs/decisions.md`; `[infra-shadow]` is the second and lives in the same commit. |

## Commands

```sh
python3 -m venv .venv
.venv/bin/pip install '.[test]'      # NOT -e, and never PYTHONPATH=src
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_conformance.py -x
.venv/bin/python -m pytest -k "marker or bound" -x
```

**Reinstall after editing `src/`.** The suite runs against an installed wheel
because this package's whole premise is being installable by other people. An
editable install would answer "is the package data present?" by looking at the
repository, which is the one question that most needs asking — and two
`isabelle-watchdog` failures showed up only under a real install.

### Verification scripts

| Script | Purpose |
|---|---|
| `scripts/probe_discovery_closure.py` | The load-set invariant over a real corpus. Run after touching `session_theories`, `_classify_import`, or the header parser. Expect `CLOSED`. |
| `scripts/build_conformance.py` | Regenerates the corpus, putting every case to `isabelle sessions -d`. Needs Isabelle on PATH. |
| `scripts/verify_move.py` | **Expired.** It differenced this package against the pre-split `isabelle_query.common`; that module now re-exports this one, so the comparison would be a function against itself. It detects this and refuses. |

## Corpora and verification habits

**Correctness is checked against Isabelle semantics, not against prior
behaviour.** Hand-compute the expected value, or ask the prover, and then make
the code match. `isabelle sessions -d DIR -a` is the oracle: it is the same
session-structure reader `isabelle build` uses, and it will tell you whether a
ROOT is even legal. Using it is how we learnt that two of the eight seed
conformance cases are inputs Isabelle *rejects*.

- `~/repos/afp/thys` — the AFP (Isabelle2025-2), 988 sessions, 9,910 theories
- `~/repos/isabelle/src` — the distribution, 135 sessions, 1,824 theories

Enumerate with `iter_sessions`, never a bare `rglob`.

**Measure before changing a classification.** Both closure fixes were sized
over both corpora first — including the containment check that showed 0
`directories` entries escape the ROOT's own directory, which is what made
widening the index safe.

## Next: a lightweight wrapper script

The planned work. **Goal: executable documentation.** The package has ten
public functions and no runnable demonstration of them — `README.md` has
snippets, the probes exercise three, and `verify_move.py` no longer runs. A
small script that uses the API the way a consumer would is worth more than
more prose, and it doubles as a smoke test that an installed wheel works.

### The open decision — `[demo-cli]`

**Does it ship, and as what?** This is in real tension with the package's
identity, so decide it deliberately and record it before writing much code.

| Option | Cost |
|---|---|
| `[project.scripts]` console script | A second public surface — flags, output format, exit codes — versioned forever. A name on `PATH`. The strongest invitation to grow into a tool. |
| `python -m isabelle_layout` (`__main__.py`) | Ships in the wheel, so it can smoke-test an install and is discoverable, but claims no name on `PATH` and is a weaker promise. **Probably the right middle.** |
| `examples/` in the sdist only | Zero promise, zero risk — and almost nobody sees it, and it cannot verify an install. |

The thing being protected: `isabelle-layout` is a *library with no opinions
beyond what the files state*. A CLI has opinions. The failure mode is becoming
`isabelle-query`-lite, at which point the split that created this package was
pointless.

### A design rule worth adopting

**The demo should touch every public name.** That gives a crisp completeness
criterion, and it tests the API rather than the implementation: if the script
cannot be written without reaching for a private import, the public surface is
wrong and that is the finding.

### Constraints, and one measured fact

- **Stdlib only.** `argparse` and `pathlib`. The no-runtime-dependencies rule
  is load-bearing, and a demo that violated it would be a poor advertisement.
- **`follow_imports` is the expensive part, by 70×.** Measured over the AFP:
  `iter_sessions` 0.31s, `session_theories` ~7s for all 988 sessions, ~0.1s
  with `follow_imports=False`. So stream output per session rather than
  collecting, and consider making the closure opt-in — a user asking "what
  sessions are here?" should not wait for an import walk.
- **Follow `wc-theories.py`'s shape**, in `~/projects/claudecode/ndtht/bin`:
  argparse, `-R/--root` defaulting to `default_t_dir()`, dedupe by resolved
  path, quiet default with a `--verbose` expansion.

### A sketch of the output, to argue with

```
$ isabelle-layout ~/repos/afp/thys/AODV
AODV                      AODV/ROOT
  parent        AWN
  base logic    HOL          (HOL-family)
  directories   variants/a_norreqid, variants/b_fwdrreps
  declared      1 theory
  builds        73 theories
```

That one view exercises `iter_sessions`, `SessionInfo`, `session_theories`,
`resolve_base_logic` and `is_hol_base`. `default_t_dir` comes from the no-
argument case, `parse_thy_imports` and `resolve_session_theory` from a
`--verbose` per-theory listing, and `conformance` from a `--self-check` mode.
`discover_roots` and `iter_thy_files` need a reason to appear — if none can be
found, that is worth knowing about the API.

### What not to build

No proof parsing, no call graph, no entry counting, no dead-code analysis, no
output formats beyond plain text. Those are `isabelle-query`'s job and it does
them well. If a flag would need `.thy` *bodies* rather than headers, it is out
of scope.

## Working boundaries

**Edits stay in this repository.** `isabelle-query` and `isabelle-watchdog`
have their own maintainers. If work here turns up a bug there, write it up as
a bug report for that project rather than patching it — the one exception
already taken was the original split, which had to touch `query` by design.

`isabelle-query` currently depends on `isabelle-layout>=0.1.0,<0.2.0` and
re-exports it from `isabelle_query.common`, so its consumers did not move on
the day of the split. Its suite (864 tests) passes against this package;
re-run it after any change to the public API:

```sh
cd ~/projects/query && .venv/bin/pip install -q ~/projects/isabelle-layout \
  && .venv/bin/python -m pytest -q
```

Note the AFP load set moved 9,907 → 9,910 with `[session-dirs]`, so downstream
census numbers shift by three theories. That is a fix, not a regression, and
it is owed to them as feedback.

## Conventions

- **Module docstrings carry the reasoning**, at length, at the top of the
  file — why the module exists and what went wrong without it. Match the
  register of `isabelle_watchdog/roots.py`, which argues its own existence.
- **Commits**: small, single-concern, frequent, with the reasoning in the
  message and a stable `[tag]` when it is a decision. Do not push unless
  asked. Trailer, verbatim:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- **Credit**: "By András Salamon, with Claude Opus 4.6, 4.7, 4.8, and 5."

## What not to do

- **Do not rewrite the tokenizer.** It is correct about nesting comments and
  cartouches in ways that are easy to get wrong and hard to notice, and each
  behaviour is scar tissue from a named file: `Universal_Turing_Machine`
  reporting an import called `*)`, `AutoCorres` importing its own `keywords`
  block, `AODV` losing 72 theories to a `theory %invisible` tag.
- **Do not add runtime dependencies.** It is what makes the package adoptable
  by tools with hard constraints of their own, which is the entire point.
- **Do not export anything "for now."**
- **Do not implement ROOT syntax Isabelle does not have.** A per-theory `in`
  clause was already deleted once for this reason; `SessionInfo.theories`'
  `dir_override` is always `None` and a test says so.
- **Do not trust a verification that cannot fail.** `verify_move.py` would
  have printed its original number while comparing functions with themselves.
  If a check passes suspiciously easily, confirm it can still fail.
