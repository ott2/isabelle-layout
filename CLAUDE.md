# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

`isabelle-layout` answers one question: **what structure does this Isabelle
project have, according to its own files?** Sessions, theory headers, project
roots — read from `ROOT` files and `.thy` headers, with no Isabelle process
involved.

**The repository is currently empty.** It holds one file,
`isabelle-layout-prompt.md`, which is the project brief and the normative
statement of scope. Read it first; this document explains what the brief
implies about the code it describes, and records what reading the source
turned up that the brief does not say.

The package does not exist yet because the code does — in the wrong place. It
is `~/projects/query/src/isabelle_query/common.py`, 1,015 lines inside an
11,470-line querying tool. Every consumer that wants a ROOT parser today
installs a query CLI to get one. This is a distribution problem, not a code
problem.

## The first commit is a move, not a rewrite

`common.py` has a real tokenizer — nesting block comments, cartouches,
per-theory `in` overrides, parent-chain resolution — and each piece of it is
scar tissue from a specific real-world ROOT or `.thy` file. The docstrings name
the encounters: `AutoCorres` swallowing a `keywords` block, `AODV` losing 72
theories to a `theory %invisible` tag, `Universal_Turing_Machine` reporting
`*)` as an imported theory, 62 of the AFP's 9,604 theories whose header sits
past any fixed head window. A rewrite rediscovers those one at a time.

So: same functions, same results, new name, first. Improvements land after, as
separate commits with tests that show the change.

## Architecture: what actually depends on what

The brief groups the extraction by cohesion. The source has a dependency
structure that cuts across those groups, and it constrains the module layout.

**The comment machinery is shared, not ROOT-specific.** `_strip_comments`
(`common.py:542`) composes `_strip_block_comments` (nesting `(* *)`),
`_strip_cartouches` (nesting `\<open> \<close>`), the legacy `{* *}` form, and
bare `\<tag>` removal. It is called by `_tokenize_root` *and* by
`parse_thy_imports`. "ROOT parsing" and "theory headers" therefore sit on one
lexer; if they become two modules, a third module underneath owns the lexer.
Duplicating it would recreate, inside this package, exactly the divergence this
package exists to end.

**`session_theories` calls `classify_import`.** The brief says take the first
and leave the second behind. `common.py:860` makes that impossible as stated —
the import-closure walk uses `classify_import` to decide which imports are
in-entry and worth following. The brief's evidence against `classify_import`
was that *no consumer outside `query` imports it*, which argues against
exporting it, not against moving it. Move it private (`_classify_import`, with
`_INFRA_ROOTS`); the public surface stays as the brief specifies.

**`iter_thy_files` needs the deprecated single-ROOT parsers.** It calls
`parse_root_theories` and `resolve_thy_file`, and the latter calls
`parse_root_directories`. All three are listed for the move, so nothing is
missing — but several functions on the public list below carry `DEPRECATED` in
their `common.py` docstrings, on the reasoning "no in-repo callers remain".
That reasoning was scoped to `query`. In this package those callers *are* the
point. Decide what deprecated means here before the first release, and write it
down.

**`default_t_dir` is independent** of all of the above — it is filesystem
search, not parsing — and is the natural seam for the bounded-vs-unbounded
decision below.

### The public surface

Defined by what consumers actually call, not by what looks tidy:
`iter_sessions`, `resolve_session_theory`, `iter_thy_files`, `default_t_dir`,
`parse_root_sessions`, `session_theories`, `is_hol_base`, `resolve_base_logic`,
`discover_roots`. Everything else stays private and stays changeable.

The failure being avoided is precisely `common`'s: a private-sounding name
doing public work, so every import feels like reaching into internals. Do not
reproduce it by exporting the whole module "for now".

## Three decisions to make before the first release

The brief states these; the source adds detail to two of them.

1. **The marker name — which is two names.** `default_t_dir` reads
   `$ISABELLE_QUERY_ROOT` *first* (`common.py:158`), then the `.isabelle-query`
   file. Renaming means renaming both, and there is a third stakeholder:
   `isabelle_watchdog/corpus.py:55` documents `.isabelle-watchdog` as
   deliberately symmetric with `.isabelle-query` — same file shape, same
   search, same place. Marker files are already committed in `~/projects/43sp`
   and `~/projects/claudecode/ndtht`. Either commit to the historical name and
   document why, or introduce a neutral one and read both for a version or two.

2. **Is `SessionInfo` public?** Much of the public surface returns or takes it.
   If public, it is a compatibility surface forever — decide what is
   guaranteed: field names, or only attribute access.

3. **What is a project root?** `default_t_dir` walks upward unboundedly, which
   suits a query tool and not every caller. `isabelle_watchdog.corpus.find_marker`
   is the same search bounded at the project root, and its comment says why:
   projects nest (`~/projects/claudecode/ndtht` inside `~/projects/claudecode`),
   and overshooting pools two repositories' data. Read that function before
   deciding. Prefer making the bound a parameter over making it a policy.

## The conformance corpus is a deliverable, not a test

Ship the ROOT/`.thy` snippets and their expected parses as **package data**.
This is what lets a consumer that cannot take a runtime dependency still
guarantee agreement — and `isabelle-watchdog` is exactly that consumer. It runs
beside a build, so an unimportable dependency means an unsupervised, unrecorded
attempt, the one outcome its design exists to prevent. It keeps its own 15-line
parser in `roots.py` and will depend on this package as a **test** dependency
only. That arrangement needs the fixture to be a shipped artefact.

The eight seed cases already exist, verified against `parse_root_sessions`, in
`~/projects/watchdog/tests/test_roots.py` (the `CONFORMANCE` table). They found
two live defects in the hand-rolled parser: a quoted name truncated at its
first space, and a bare name truncated at its first `.` or `-`. Grow the table
from real ROOTs; `query-private/bin/afp_census.py` already walks the AFP and
the distribution.

## Packaging and commands

Nothing is set up yet. Mirror `~/projects/watchdog` (`isabelle-watchdog`),
which the brief names as the model: hatchling, src-layout, version
single-sourced from `__init__.py` via `[tool.hatch.version]`,
`[project.optional-dependencies] test`, pytest with `-ra --strict-markers`,
`docs/` in the sdist. Copy its `pyproject.toml` and adjust.

```sh
python3 -m pip install -e .          # once packaging exists
python3 -m pip install --group test  # or the `test` extra, per which form is chosen
python3 -m pytest                    # whole suite
python3 -m pytest tests/test_roots.py::test_name -x   # one test
```

**No runtime dependencies.** `common.py` has none, `query` has none, and a
parsing library that pulls in a tree is one that consumers route around. Test
dependencies are not runtime ones; a `[test]` extra is fine.

**Test against a real install** — `pip install .` into a fresh venv — not
`PYTHONPATH=src`. `query`'s suite uses a `sys.path` shim (`tests/support.py`),
and two watchdog failures showed up only under a real install. This package's
whole premise is being installable by other people, so the install path is the
one under test.

## Migration: no flag day

Scripts in `~/projects/claudecode/ndtht/bin` and
`~/projects/claudecode/query-private/bin` import `isabelle_query.common`
directly, as do `query`'s own `parsing`, `cli`, and `commands`. Have `query`
depend on this package and re-export from `common` for a deprecation window, so
nothing breaks on the day of the split. Move consumers individually afterwards,
at whatever pace suits.

`query`'s existing tests for the moved code come too:
`tests/test_discover_roots.py`, `test_session_theories.py`, `test_base_logic.py`,
`test_thy_header.py`, `test_bad_root.py`. They currently use `unittest` plus the
`support.py` path shim; converting them to plain pytest against an installed
package is part of the move.

## Conventions inherited from the sibling repos

- **Design decisions live in commit messages**, cross-referenced by a stable
  `[tag]` — `git log --grep='\[marker-name\]'`. `query` keeps no changelog and
  no decision archive, on the grounds that a summary of a commit drifts from it
  and the commit does not. `isabelle-watchdog` does keep a `CHANGELOG.md`;
  pick one deliberately.
- **Module docstrings carry the reasoning.** Both siblings state *why* a module
  exists and what went wrong without it, at length, at the top of the file.
  `isabelle_watchdog/roots.py` is the clearest example — it argues its own
  existence against importing `common`. Match that register.
- **Commits**: small, single-concern, frequent. Do not push unless asked.
  Trailer, verbatim:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- **Correctness is checked against Isabelle semantics**, not against prior
  behaviour — hand-compute a fixture value first, then make the code match.
  The AFP checkout at `~/repos/afp/thys` (Isabelle2025-2) is the corpus;
  enumerate it with `iter_sessions`, never a bare `rglob`.
- **Credit**: "By András Salamon, with Claude Opus 4.6, 4.7, 4.8, and 5."

## What not to do

- Do not rewrite the tokenizer. It is correct about nesting comments and
  cartouches in ways that are easy to get wrong and hard to notice.
- Do not move `run_guarded` (`common.py:175`). Six lines, not Isabelle-specific,
  already deprecated in place, already copied into `isabelle_watchdog/guard.py`.
  Do not give it a third home.
- Do not export everything "for now". The current situation is what that
  produces.
- Do not break the consumers on day one.
