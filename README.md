# isabelle-layout

**What structure does this Isabelle project have, according to its own files?**

Sessions, theory headers, project roots — read from `ROOT` files and `.thy`
headers, with no Isabelle process involved. No prover is started, no heap is
built, and none needs to have been built. The answers come from the text the
project itself commits.

```python
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
parent chain — and it was correct in places a regex is not, because each of
those behaviours is scar tissue from a specific real ROOT or `.thy` file.

The problem was never the code. It was that every consumer who wanted a ROOT
parser had to install a query CLI to get one, and thereby inherit its release
cadence, its version floor, and its userbase's compatibility constraints. A
library shipped inside an application is a library that can only be adopted by
people willing to adopt the application.

That cost was not hypothetical. `isabelle-watchdog` runs beside an Isabelle
build, and takes **no runtime dependencies on purpose** — anything it imports
is something that can break a build, and an unsupervised, unrecorded build is
the one outcome its entire design exists to prevent. So it wrote its own
15-line ROOT parser rather than depend on a correct one. That parser had two
real defects: a quoted session name truncated at its first space, so a session
built as `Probe (AFP)` was recorded against a session named `Probe`; and a bare
name truncated at its first `.` or `-`, so `HOL-Analysis` became `HOL`. Nothing
downstream could tell.

A separate package does not make that consumer's constraint go away, and it is
not meant to. It gives it a second option: depend on this as a **test**
dependency and assert agreement in CI against the conformance corpus this
package ships as package data. The hand-rolled
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
analysis. So the classifier that `isabelle-query`'s AFP census uses came across
only as a private implementation detail of the import closure, and is not part
of the public API.

The one exception is documented where it lives: `isabelle_layout.distribution`
holds facts about the *Isabelle distribution* (which object logics are not HOL)
rather than about the project being read. A hardcoded set of distribution
session names ages differently from a parser, so it is a separate module and
says so.

## Installing

```sh
python3 -m pip install isabelle-layout
```

No runtime dependencies, deliberately. Python 3.9 and up.

## Credit

By András Salamon, with Claude Opus 4.6, 4.7, 4.8, and 5.
