# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

This file is what a session starts from: what the package is, how it is shaped,
and the rules that hold. It is deliberately **not** a log. Release history,
measurements and the reasoning behind past changes live in the git log, indexed
by `docs/decisions.md`; a number quoted here would be stale by the time anyone
relied on it.

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
| `[demo-cli]` | Ships as a **console script**, not `python -m` and not an unshipped example. Bounded by a rule enforced in `tests/test_cli.py`: every flag reaches a public function, and no private name is imported. |

## Commands

```sh
python3 -m venv .venv
.venv/bin/pip install '.[test]'      # NOT -e, and never PYTHONPATH=src
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_conformance.py -x
.venv/bin/python -m pytest -k "marker or bound" -x
.venv/bin/isabelle-layout --self-check     # smoke-test the installed wheel
```

**Reinstall after editing `src/`.** The suite runs against an installed wheel
because this package's whole premise is being installable by other people. An
editable install would answer "is the package data present?" by looking at the
repository, which is the one question that most needs asking — and two
`isabelle-watchdog` failures showed up only under a real install.

### Verification scripts

| Script | Purpose |
|---|---|
| `scripts/probe_against_isabelle.py` | **The strongest check there is**: `session_theories` against `isabelle build -n -l`, the real build's own dependency resolution. Expect `AGREES`. Needs Isabelle; ~5 min for the AFP. |
| `scripts/probe_discovery_closure.py` | The load-set invariant over a real corpus. Needs no prover, and so can run anywhere — but a set uniformly too small satisfies it. Expect `CLOSED`. |
| `scripts/build_conformance.py` | Regenerates the corpus, putting every case to `isabelle sessions -d`. Needs Isabelle on PATH. |
| `scripts/verify_move.py` | **Expired.** It differenced this package against the pre-split `isabelle_query.common`; that module now re-exports this one, so the comparison would be a function against itself. It detects this and refuses. |

## Corpora and verification habits

**Correctness is checked against Isabelle semantics, not against prior
behaviour.** Hand-compute the expected value, or ask the prover, and then make
the code match. There are two oracles, and they answer different questions:

- **`isabelle sessions -d DIR -a`** — what a ROOT *declares*, and whether it is
  even legal. Using it is how we learnt that some of the seed conformance cases
  are inputs Isabelle *rejects*.
- **`isabelle build -n -l`** — what a session *loads*, file by file. This is
  the authority for `session_theories`, and it settles questions that reading
  `Pure/Build/sessions.scala` only half-answers. It established that a
  `directories` entry may leave the ROOT's own directory, that a bare import is
  looked up in the declared directories and not recursively, and that two
  sessions claiming one directory is an error Isabelle raises
  (`Duplicate use of directory`) rather than something a reader must guard
  against.

Two corpora are on this machine. Enumerate them with `iter_sessions`, never a
bare `rglob`:

- `~/repos/afp/thys` — the AFP, Isabelle2025-2
- `~/repos/isabelle/src` — the Isabelle distribution

**Do not quote an agreement figure from documentation — run the probe.**
`scripts/probe_against_isabelle.py` is what establishes whether this package
still agrees with `isabelle build -n -l` over those corpora, and it is the only
answer that cannot be out of date.

**Measure before changing a classification.** Size the change over both corpora
first. A rule that looks obviously right against one ROOT can move theories by
the hundred across the AFP, in either direction, and the difference between a
fix and a regression is not visible from a single example.

## The CLI — `[demo-cli]`, decided

`isabelle-layout` ships as a **console script** (`[project.scripts]` →
`isabelle_layout._cli:main`). It exists for two readers: a maintainer wanting
executable documentation of the API, and an **LLM orienting itself in a
repository that carries Isabelle proofs as ancillary artefacts** — a growing
case, and one that discovers a command on `PATH` but not an import path. That
second reader is why the weaker `python -m` option was not taken.

**What bounds it is a rule, not restraint: every flag exists to reach a public
function.** So the command cannot grow without the library growing first, and
"would this need a new public function?" has an answer. `tests/test_cli.py`
enforces the rule by AST — every name in `__all__`, plus both distribution
predicates and `conformance`, must be *imported and referenced*, and no
private name may be reached at all.

```
$ isabelle-layout ~/repos/afp/thys/AODV
AODV
  root         ROOT
  parent       AWN
  base logic   AWN  (not a distribution logic; the parent chain probably leaves the scanned directory)
  directories  variants/a_norreqid, variants/b_fwdrreps, …
  declared     1 theory   All
  builds       73 theories
```

| Flag | Public name it reaches |
|---|---|
| *(default)* | `iter_sessions`, `SessionInfo`, `session_theories`, `resolve_base_logic`, `resolve_session_theory`, `is_hol_base`, `is_known_nonhol_base` |
| *(no PATH)* | `default_t_dir` |
| *(PATH is a ROOT)* | `parse_root_sessions` |
| `-v` | `parse_thy_imports` |
| `--roots` | `discover_roots` |
| `--files` | `iter_thy_files` |
| `--self-check` | `conformance` |
| `-l`, `--no-closure` | none — they *withhold* the 70× cost |

**The weakest-justified name on the surface is `iter_thy_files`.**
`iter_sessions` + `session_theories` subsume it except for the one thing
`--files` uses — declared theories, ROOT order, deduplicated, no closure. Real,
but narrow. If the public surface is ever revisited, that is the name to
revisit first.

Two behaviours worth keeping:

- **Base logic reports three states, not two.** `is_hol_base` and
  `is_known_nonhol_base` are not each other's negation, so a base that is
  neither is said to be neither. Pointing at one AFP entry gives
  `AWN (not a distribution logic…)`; pointing at `~/repos/afp/thys` gives
  `HOL (HOL family)`, because the parent chain is now in scope. The message
  says so instead of guessing.
- **A declared theory with no file on disk is flagged.** Isabelle refuses to
  build that ROOT; a reader that silently returned fewer theories would give a
  plausible, short answer.

### What not to build

No proof parsing, no call graph, no entry counting, no dead-code analysis, no
output formats beyond plain text. Those are `isabelle-query`'s job and it does
them well. If a flag would need `.thy` *bodies* rather than headers, it is out
of scope. Stdlib only — `argparse` and `pathlib`; the no-runtime-dependencies
rule is load-bearing and a demo that broke it would be a poor advertisement.

## Working boundaries

**Edits stay in this repository.** `isabelle-query` and `isabelle-watchdog`
have their own maintainers. If work here turns up a bug there, write it up as
a bug report for that project rather than patching it — the one exception
already taken was the original split, which had to touch `query` by design.

`isabelle-query` declares `isabelle-layout>=0.2.0` — floor, no ceiling — and
re-exports this package from `isabelle_query.common`, so its consumers did not
move on the day of the split. Re-run its suite after any change to the public
API:

```sh
cd ~/projects/query && .venv/bin/pip install -q ~/projects/isabelle-layout \
  && .venv/bin/python -m pytest -q
```

A change here that moves a load set moves their census numbers too. That is
owed to them as feedback, whether it is a fix or a regression.

### The open question — `[layout-privates]`

`isabelle_query/common.py` imports underscore-private names from this package:
`_tokenize_root`, `_resolve_thy_file`, `_parse_root_theories`,
`_parse_root_directories`, `_read_marker`, `_INFRA_ROOTS`, `_THY_HEADER_RE`,
`_NONHOL_DISTRIBUTION_BASES`, `_classify_import`, `LEGACY_MARKER_NAME`, and the
whole of `_lexer`. Its `tests/test_layout_surface.py` pins them from the
outside, resolving each through `importlib` so a removal names the casualty
instead of failing as one `ImportError` from whichever test imported first.

**This package's rule is that the public API is named by evidence — what
consumers actually import.** By that rule the surface is wrong, and no version
range fixes it: a *patch* release may move any of those names.

Settle it before the next change to any of them. Both obvious answers fight
recorded decisions: promoting `_classify_import` reverses the documented reason
it is private (an analysis judgement, not a reading of a file), and promoting
`_INFRA_ROOTS` publishes the name list `distribution.py` exists to keep
separable. A third option is an explicitly-unstable `isabelle_layout._compat`
naming exactly these, which keeps the judgement private while making the
dependency legible and breakage deliberate.

## Releasing

`docs/publishing.md` is the runbook. In outline: drop the `.dev0` from
`version` in `pyproject.toml` and reinstall, commit with the release notes *as
the commit message*, `git push origin main`, `git push origin vX.Y.Z`. The tag
push triggers `.github/workflows/release.yml`, which publishes the GitHub
Release from that commit's message. PyPI is a separate manual `twine upload`.

The version is declared once, statically, in `pyproject.toml`;
`isabelle_layout.__version__` reads it back from the installed distribution
metadata, resolved on access by a module `__getattr__`. Between releases `main`
carries a `.dev0` suffix, because a tree that is not the published release must
not claim to be it.

**Release when there is something worth releasing, not once per fix.** Fixes
accumulate on `main`; outside users will find things worth fixing, and a
release each would be churn.

**There is no CI matrix.** So `requires-python = ">=3.9"` and the classifiers
through 3.14 are verified *statically only* — every module must parse under
`ast.parse(feature_version=(3, 9))`, all carry `from __future__ import
annotations`, and there must be no runtime PEP 604, no match statement, and no
post-3.9 stdlib call. Only 3.14 is installed on this machine. Adding the matrix
is the first thing worth doing.

## Conventions

- **Module docstrings carry the reasoning**, at length, at the top of the
  file — why the module exists and what went wrong without it. Match the
  register of `isabelle_watchdog/roots.py`, which argues its own existence.
  `pyproject.toml` is the exception and carries none: it is read by people
  debugging a build, who arrive without the context an argument would need.
- **Never rewrite history.** No `git commit --amend`, no `git reset`, no
  force-push, and no merge whose purpose is to repair an earlier rewrite. A
  pushed commit with an imperfect message stays as it is: *"no-one is grading
  our work; our users care about releases being good quality and not how they
  got there."* If something about a release needs restating, add — a new
  commit and a new version. Version numbers before publication are free;
  history other people may have fetched is not.
- **The release notes are the version-bump commit's message.**
  `.github/workflows/release.yml` publishes that commit's message as the GitHub
  Release, so it is written for *users* — what changed since the last release —
  while how the work happened goes in the commits around it. Not the tag
  annotation: the workflow dereferences the tag to its commit precisely because
  reading annotations is unreliable on a runner.
- **Avoid `gh`. The release workflow exists so that no local step needs it**:
  plain git over SSH pushes branches and tags, and CI creates the Release from
  the tagged commit's message. Reach for `gh` only for work that exists
  nowhere but GitHub's database and has no other route — **issues above all**,
  both reading them and posting them, which is how a bug found here reaches
  `isabelle-query` or `isabelle-watchdog` (see **Working boundaries**). Two
  limits: `ott2/*` repositories only, and nothing destructive — no deleting or
  editing releases, tags, branches, runs or repositories, no `gh api -X
  DELETE/PATCH/PUT`, and not `gh release create`, which would move the release
  notes off the commit message.
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
- **Do not ship this project's release process in the sdist.**
  `docs/publishing.md` and `scripts/verify_move.py` are excluded because they
  are about releasing this package rather than about the code, and somebody
  building from source has no use for either. Both stay in the repository.
- **Do not add `.gitignore` to the sdist `exclude` list.** It was tried;
  hatchling ships the file regardless. A config line that does nothing is worse
  than the file it fails to remove, because the next reader believes it.
- **Do not trust a verification that cannot fail.** `verify_move.py` would
  have printed its original number while comparing functions with themselves.
  If a check passes suspiciously easily, confirm it can still fail.
