# isabelle-layout

**What structure does this Isabelle project have, according to its own files?**

Sessions, theory headers and project roots, read from `ROOT` files and `.thy`
headers. No Isabelle process is started, no heap is built, and none needs to
exist.

```python
from pathlib import Path
from isabelle_layout import iter_sessions, session_theories

for session in iter_sessions(Path("~/repos/afp/thys").expanduser()):
    print(session.name, len(session_theories(session)))
```

That it needs no prover is the point: this runs in CI with no Isabelle
installed, in a packaging script, in an editor plugin, or in an agent orienting
itself in an unfamiliar repository. Reading a `ROOT` takes milliseconds where
building a heap takes minutes.

## Install

```sh
python3 -m pip install isabelle-layout
```

Python 3.9 and up. No runtime dependencies, deliberately: the package exists so
that tools with hard constraints of their own can adopt a correct ROOT parser
rather than hand-roll a regex.

```sh
isabelle-layout --self-check     # confirm the install against its own corpus
```

## API

Ten names, and `__all__` is pinned by a test, so the surface changes only
deliberately. `py.typed` ships, so the annotations below are visible to type
checkers.

| | |
|---|---|
| `iter_sessions(root_dir) -> list[SessionInfo]` | every session declared by any `ROOT` beneath a directory |
| `discover_roots(root_dir) -> list[Path]` | the `ROOT` files, scoped exactly as `isabelle build -D` scopes them |
| `parse_root_sessions(root_path) -> list[SessionInfo]` | every `session` declaration in one `ROOT` |
| `session_theories(session, *, follow_imports=True) -> list[tuple[str, Path]]` | what a session builds — declared roots plus their in-entry import closure |
| `resolve_session_theory(session, entry) -> Path \| None` | a declared theory's `.thy` file on disk, or `None` |
| `parse_thy_imports(thy_path) -> list[str]` | a theory's `imports` clause |
| `iter_thy_files(t_dir=None) -> list[Path]` | the `.thy` files a directory's `ROOT`s declare |
| `resolve_base_logic(name, parents) -> str` | follow a session's parent chain to its distribution root |
| `default_t_dir(start=None, *, bound=None) -> Path` | which directory is the project |
| `SessionInfo` | one parsed session declaration |

Plus `from isabelle_layout.distribution import is_hol_base,
is_known_nonhol_base`, kept off the top level because a hardcoded list of
distribution session names ages differently from a parser — the import line
says which kind of claim you are relying on. The two are **not** each other's
negation: a base that is neither is a base this package will not guess about.

### `SessionInfo`

```python
session.name            # str
session.root_path       # Path   — the ROOT file this came from
session.session_dir     # Path   — property; where its theories live
session.parent          # str | None
session.used_sessions   # list[str]
session.directories     # list[str]
session.in_subdir       # str | None
session.theories        # list[tuple[str, str | None]]  — declared entries
```

Those attribute **names and types are the contract**, along with the
`session_dir` property and construction by keyword. Not promised: that it is a
`dataclass`, nor its equality, ordering, hashing, `repr`, field order or
mutability. If you need to know whether two values name the same session,
compare `(name, root_path)`.

The boundary is drawn at *what a file says*. Reading a `ROOT` and reporting the
sessions it declares is a fact about the file; deciding which of a theory's
imports count as "infrastructure" is an analysis judgement, and belongs to the
tool doing the analysis.

### Compatibility — pin a floor, not a ceiling

What is promised, so you do not have to guess:

- **`__all__` is pinned by a test.** A name cannot leave the surface by
  accident; a removal is deliberate and arrives with a minor bump.
- **`SessionInfo`'s field names and types**, as above. New attributes, if any
  are ever added, are appended with defaults, so keyword construction keeps
  working.
- **No runtime dependencies**, so nothing arrives transitively.

Anything underscore-prefixed is private and may move in a patch release.

An upper bound is not needed for that and costs more than it saves. It cannot
detect a break — only prevent an install — and it propagates to your own
consumers, who inherit a ceiling they did not choose. What detects a break is
running your test suite against this package; a version range only decides when
you are allowed to find out.

### Why `session_theories` and not a `*.thy` glob

A ROOT usually under-states what a session builds. AFP's `AODV` declares
**one** theory and builds **73**; the rest arrive through `imports`. A glob has
the opposite failure — it sweeps up orphan, scratch and archived `.thy` files
that `isabelle build` never compiles.

Import-reachability from the declared roots is the set that matches the build,
and that is checked rather than asserted: `scripts/probe_against_isabelle.py`
compares it against `isabelle build -n -l`, the real build's own dependency
resolution, across the whole of the AFP and the Isabelle distribution — 988 and
132 sessions respectively, against Isabelle2025-2.

## Command line

`pip install` puts `isabelle-layout` on your `PATH`. One command answers "what
Isabelle is in this tree?" — the question you have when orienting yourself in a
repository that carries proofs as ancillary artefacts.

```
$ isabelle-layout ~/repos/afp/thys/Ordinary_Differential_Equations
/…/Ordinary_Differential_Equations — 1 ROOT file, 7 sessions

Ordinary_Differential_Equations
  root         ROOT
  parent       HOL-Analysis
  base logic   HOL-Analysis  (HOL family)
  uses         HOL-Decision_Procs, Triangle, List-Index, Affine_Arithmetic
  directories  Library, IVP
  declared     1 theory   ODE_Analysis
  builds       17 theories
…
```

| | |
|---|---|
| `-l, --list` | one line per session; skips the import closure, which costs ~70× the rest |
| `-v, --verbose` | every theory a session builds, with its imports |
| `--no-closure` | omit `builds` |
| `--roots` | the `ROOT` files, one per line |
| `--files` | the declared theory files — a session's entry points — one per line |
| `--self-check` | check this installation against the conformance corpus inside it |

With no `PATH` it uses `default_t_dir()`. Exit status: 0 found something, 1
found nothing, 2 bad usage.

Every flag exists to reach a public function, and a test enforces that. The
command is a demonstration of the library, not a tool in its own right — for
analysis of the proofs themselves (call graphs, dead code, entry census),
`isabelle-query` is the tool.

## Conformance corpus

`isabelle_layout/data/conformance.json` ships **inside the wheel**, so another
implementation can check itself against it without taking a runtime dependency
it cannot afford:

```python
from isabelle_layout import conformance

for case in conformance.cases(accepted_only=True):
    assert my_parser(case["root"]) == conformance.session_names(case)
```

Every case was put to `isabelle sessions -d` and carries the verdict.
`"accepts"` means there is a ground truth and a parser that disagrees is wrong;
`"rejects"` means `isabelle build` refuses the input, so the case pins
robustness rather than a value — a session name may not contain spaces or
parentheses, and a *bare* name may not contain `-`, which lexes as a symbolic
identifier. `scripts/build_conformance.py` regenerates the corpus against
whatever Isabelle is on `PATH`.

## Developing

```sh
python3 -m venv .venv
.venv/bin/pip install '.[test]'    # not -e: a wheel is what consumers get
.venv/bin/python -m pytest         # reinstall after editing src/
```

Non-editable on purpose: an editable install answers "is the package data
present?" by looking at the repository, which is the one question that most
needs asking — a corpus correct in `src/` and absent from the wheel is a corpus
no consumer can use.

Design decisions live in commit messages, indexed by `docs/decisions.md` and
findable by tag:

```sh
git log --grep='\[marker-name\]'
```

`isabelle-query` and `isabelle-watchdog` both depend on this package, and both
import only its public names.

## Licence

MIT. By András Salamon, with Claude Opus 4.6, 4.7, 4.8, and 5.
