# isabelle-layout

**What structure does this Isabelle project have, according to its own files?**

Sessions, theory headers, project roots — read from `ROOT` files and `.thy`
headers, with no Isabelle process involved. No prover is started, no heap is
built, and none needs to have been built. The answers come from the text the
project itself commits.

```python
from pathlib import Path
from isabelle_layout import iter_sessions, session_theories

for session in iter_sessions(Path("~/repos/afp/thys").expanduser()):
    print(session.name, len(session_theories(session)))
```

## Why is this not part of isabelle-query?

Because it was, and that was the wrong door.

The code here is `isabelle_query.common`, near enough verbatim: 1,015 lines of
ROOT tokenizer and theory-header reader inside an 11,000-line *querying tool*.
It is good code — it nests block comments and cartouches correctly, it knows
that `keywords` is a header clause and not an import, it resolves a session's
parent chain — and it is correct in places a regex is not, because each of
those behaviours is scar tissue from a specific real `ROOT` or `.thy` file.

The problem was never the code. It was that every consumer who wanted a ROOT
parser had to install a query CLI to get one, and thereby inherit its release
cadence, its version floor, and its userbase's compatibility constraints. A
library shipped inside an application is a library that can only be adopted by
people willing to adopt the application.

That cost was not hypothetical. `isabelle-watchdog` runs beside an Isabelle
build and takes **no runtime dependencies on purpose** — anything it imports is
something that can break a build, and an unsupervised, unrecorded build is the
one outcome its entire design exists to prevent. So it wrote its own 15-line
ROOT parser rather than depend on a correct one. That parser had two real
defects: a quoted session name truncated at its first space, so a session built
as `Probe (AFP)` was recorded against a session named `Probe`; and a bare name
truncated at its first `.` or `-`, so `HOL-Analysis` became `HOL`. Nothing
downstream could tell.

A separate package does not make that consumer's constraint go away, and is not
meant to. It gives it a second option: depend on this as a **test** dependency
and assert agreement in CI against the [conformance
corpus](#the-conformance-corpus) shipped as package data. The hand-rolled
parser stays; what changes is that its divergence from a correct one becomes a
failing test rather than a silent mis-attribution.

So the split is not about the code being in the wrong file. It is about who is
allowed to use it:

- **`isabelle-query`** answers *what is in these proofs* — entries, call graph,
  dependencies, dead code. It is a tool, it has opinions, and it releases when
  its users need it to.
- **`isabelle-layout`** answers *what does this project say it is*. It is a
  library, it has no opinions beyond what the files state, and it has no
  runtime dependencies at all.

`isabelle-query` depends on this package and re-exports it from
`isabelle_query.common`, so nothing broke on the day of the split.

## Scope: files, not judgements

The boundary is deliberate and it is drawn at *what a file says*.

Reading a `ROOT` and reporting the sessions it declares is a fact about the
file. Deciding which of a theory's imports count as "infrastructure" is an
analysis judgement — reasonable, useful, and belonging to the tool doing the
analysis. So the classifier `isabelle-query`'s AFP census uses came across only
as a private implementation detail of the import closure, and is not public.

The one exception documents itself where it lives:
`isabelle_layout.distribution` holds facts about the *Isabelle distribution*
(which object logics are not HOL) rather than about the project being read. A
hardcoded set of distribution session names ages differently from a parser, so
it is a separate module, and it is deliberately not re-exported at the top
level — the import line says which kind of claim you are relying on.

## The public API

Named by evidence: these are what the twelve consuming scripts across two
repositories actually import.

| | |
|---|---|
| `iter_sessions(root_dir)` | every session declared by any `ROOT` beneath a directory |
| `discover_roots(root_dir)` | the `ROOT` files, scoped exactly as `isabelle build -D` scopes them |
| `parse_root_sessions(root_path)` | every `session` declaration in one `ROOT` |
| `resolve_session_theory(session, entry)` | a declared theory's `.thy` file on disk |
| `session_theories(session)` | what a session actually builds — declared roots plus their in-entry import closure |
| `parse_thy_imports(thy_path)` | a theory's `imports` clause |
| `iter_thy_files(t_dir)` | the `.thy` files a directory's `ROOT`s declare |
| `resolve_base_logic(name, parents)` | follow a session's parent chain to its distribution root |
| `default_t_dir(start, *, bound)` | which directory is the project |
| `SessionInfo` | one parsed session declaration |

`from isabelle_layout.distribution import is_hol_base, is_known_nonhol_base`
for the two distribution predicates.

Everything else is private and stays changeable. `__all__` is pinned by a test
(`tests/test_public_api.py`), so adding to the surface is a deliberate act and
removing from it fails loudly — which is precisely what `common` could not do.

The package ships `py.typed`, so the annotations above are visible to type
checkers rather than decorative.

### Why `session_theories` and not a `*.thy` glob

Because a ROOT usually under-states what a session builds. AFP's `AODV`
declares **one** theory and builds **73**; the rest arrive through `imports`.
A glob has the opposite failure: it sweeps up orphan, scratch and archived
`.thy` files that no declared root imports and that `isabelle build` never
compiles. Import-reachability from the declared roots is the set that matches
the build.

## The conformance corpus

`isabelle_layout/data/conformance.json` ships **inside the wheel** — package
data, not a test fixture.

The difference is the deliverable. A fixture proves this package is right; a
shipped corpus lets somebody else prove they agree with it, without taking a
runtime dependency they cannot afford.

```python
from isabelle_layout import conformance

for case in conformance.cases(accepted_only=True):
    assert my_parser(case["root"]) == conformance.session_names(case)
```

Every case was put to `isabelle sessions -d` — the same session-structure
reader `isabelle build` uses — and carries the verdict:

- **`"accepts"`** — Isabelle parses this `ROOT` and declares these sessions.
  There is a ground truth, and a parser that disagrees is wrong.
- **`"rejects"`** — `isabelle build` refuses this `ROOT`. There is no ground
  truth to conform to, and the case pins *robustness*: readers still must not
  each invent a different silent renaming of malformed input.

That distinction is not decoration. Two of the eight cases this corpus was
seeded with turned out to be inputs Isabelle rejects outright — a session name
may not contain spaces or parentheses, and a *bare* name may not contain `-`,
which lexes as a symbolic identifier. They had been verified against a parser,
not against Isabelle. Both are kept, correctly labelled, because they are the
two live defects the corpus exists to prevent.

The remaining cases are grown from real `ROOT`s, chosen by counting shapes
across 979 of them rather than by imagination. `scripts/build_conformance.py`
regenerates and re-verifies against whatever Isabelle is on `PATH`.

## Installing

```sh
python3 -m pip install isabelle-layout
```

No runtime dependencies, deliberately. Python 3.9 and up — the floor is
`isabelle-query`'s, because a library whose floor is higher than its first
consumer's is one that consumer cannot adopt.

## Developing

The suite runs against a real install, never `PYTHONPATH=src`. This package's
whole premise is being installable by other people, so the install path is the
one under test — and two `isabelle-watchdog` failures showed up only that way.

```sh
python3 -m venv .venv
.venv/bin/pip install '.[test]'    # not -e: a wheel is what consumers get
.venv/bin/python -m pytest         # re-run the install after editing src/
```

Non-editable on purpose. An editable install still maps the source tree, so it
answers "is the package data present?" by looking at the repository — which is
the one question that most needs asking, since a corpus correct in `src/` and
absent from the wheel is a corpus no consumer can use.

Design decisions live in commit messages, indexed by `docs/decisions.md` and
findable by tag:

```sh
git log --grep='\[marker-name\]'
```

## Credit

By András Salamon, with Claude Opus 4.6, 4.7, 4.8, and 5.
