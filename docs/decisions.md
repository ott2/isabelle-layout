# Decisions

## Where the reasoning lives, and why it is not here

**In the commit messages.** This file is an *index*, not a summary.

The two sibling repositories do this differently and the choice was made
deliberately rather than by copying whichever was nearer.
[`isabelle-watchdog`](https://github.com/salamon/isabelle-watchdog) keeps a
`CHANGELOG.md`; `isabelle-query` keeps neither a changelog nor a decision
archive, on the grounds that a summary of a commit drifts from the commit and
the commit does not.

This package follows `isabelle-query`, for a reason specific to what it is. Its
decisions are almost all about *why a behaviour is what it is* — why the
nearest marker wins over the neutrally-named one, why two predicates about HOL
default in opposite directions, why a slot in a public dataclass is always
`None`. That kind of reasoning belongs next to the change that introduced it,
where it cannot silently stop describing the code. A file that restated it
would eventually disagree with the code and be believed anyway, because it
reads like documentation.

So this file contains no reasoning at all. It contains the tags, so that

```sh
git log --grep='\[marker-name\]'
```

finds the argument in full. What the tags cannot capture — the shape of the
package, and the standing rules — is in the module docstrings, which is where
both siblings put it.

## The three decisions before the first release

| Tag | Question | Answer |
|-----|----------|--------|
| `[marker-name]` | Is the marker file still called `.isabelle-query`? | No. `.isabelle-layout` and `$ISABELLE_LAYOUT_ROOT` are primary; the historical spellings are read as aliases, permanently. Both names are tested at *each level* of the upward walk, so proximity beats spelling. |
| `[session-info]` | Is `SessionInfo` public, and what is guaranteed? | Public — four of the ten public functions take or return it. Guaranteed: the seven attribute *names* and types, `session_dir`, and keyword construction. Not guaranteed: dataclass-ness, equality, ordering, hashing, `repr`, field order, mutability. |
| `[root-bound]` | How far up does the search for a project root go? | As far as the caller says. Unbounded by default, `bound=` on request. Not a git dependency: the caller computes the boundary and passes a `Path`. |

## Standing decisions, recorded in code rather than here

These are pinned by tests, so they cannot drift; the test is the record.

| Decision | Pinned by |
|----------|-----------|
| The public API is exactly what consumers import, and nothing else | `tests/test_public_api.py` |
| `is_hol_base` / `is_known_nonhol_base` are public but not re-exported at top level — a hardcoded list of distribution names ages differently from a parser | `test_distribution_predicates_are_public_but_not_re_exported` |
| `classify_import` is private: it is an analysis judgement, not a reading of a file | `test_the_analysis_judgement_did_not_become_public` |
| `run_guarded` did not move | `test_run_guarded_did_not_come_along` |
| `SessionInfo.theories`' `dir_override` is always `None` — Isabelle has no per-theory `in` clause | `test_the_dir_override_slot_is_always_none` |
| The conformance corpus is in the *wheel*, not just the repository | `test_the_corpus_ships_inside_the_installed_package` |

## The one number worth keeping

The move out of `isabelle_query.common` was verified rather than asserted:

```
AFP (Isabelle2025-2)      958 ROOTs   988 sessions   9984 theories
Isabelle distribution      18 ROOTs   135 sessions   1851 theories
--------------------------------------------------------------------
68362 comparisons, 0 disagreements
```

`scripts/verify_move.py` produced it, and **can no longer reproduce it**:
`isabelle_query.common` now re-exports this package, so the two
"implementations" are the same function objects and the comparison would pass
vacuously — 68,362 checks of a function against itself, printing the same
number as the real run. The script detects that and refuses rather than
reporting a result it did not earn. Reproducing it means checking `common.py`
out at `isabelle-query`'s last pre-split commit.

That expiry is the argument for the conformance corpus being a shipped
artefact rather than a script: the corpus keeps working when the thing it was
differenced against is gone.
