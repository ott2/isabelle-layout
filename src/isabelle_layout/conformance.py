"""conformance.py — the agreement, shipped.

`data/conformance.json` is **package data**, not a test fixture, and the
difference is the whole point of it.

A test fixture proves this package is right. A shipped corpus lets somebody
*else* prove they agree with it — which matters because the most important
consumer cannot import this package at runtime and never will.
`isabelle-watchdog` runs beside an Isabelle build and declares no runtime
dependencies on purpose: anything it imports is something that can break a
build, and an unsupervised, unrecorded build is the exact outcome its design
exists to prevent. So it keeps its own 15-line ROOT reader and depends on this
package as a **test** dependency only, asserting agreement in CI.

That arrangement works only if the fixture is an artefact. Hence a JSON file
inside the wheel, and this loader.

Two kinds of case, and they must not be confused
------------------------------------------------

Each case records what ``isabelle sessions -d`` said about its ROOT, under
``isabelle``:

``"accepts"``
    Isabelle parses this ROOT and declares these sessions. There is a ground
    truth and ``expect`` matches it. A parser that disagrees is **wrong**.

``"rejects"``
    ``isabelle build`` refuses this ROOT outright, so there is no ground truth
    to conform to. ``expect`` is what *this* package does with it, and the
    case exists because readers still have to agree on malformed input rather
    than each inventing a different silent renaming. Two of the cases the
    corpus was seeded with are of this kind — they were presented as verified
    Isabelle behaviour and are not.

A consumer asserting conformance should use the ``accepts`` cases. One
asserting bug-for-bug agreement may use both, knowingly.

Using it
--------

    from isabelle_layout import conformance

    for case in conformance.cases(accepted_only=True):
        assert my_parser(case["root"]) == conformance.session_names(case)

Cases are plain dicts, mirroring the JSON exactly. That is deliberate: the
artefact is the file, this module is a convenience, and wrapping it in a class
would add a second public type whose shape then has to be promised forever.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_PACKAGE = "isabelle_layout.data"
DATA_NAME = "conformance.json"


def _read() -> str:
    """The corpus as text, from the installed package.

    `importlib.resources` rather than `__file__` arithmetic, so this keeps
    working when the package is installed as a zip or loaded by something
    other than the plain filesystem loader.
    """
    from importlib import resources
    return (resources.files(DATA_PACKAGE) / DATA_NAME).read_text(encoding="utf-8")


def load() -> dict:
    """The whole corpus: ``{"schema", "verified_against", "cases"}``.

    ``verified_against`` names the Isabelle release whose
    ``isabelle sessions -d`` produced the ``isabelle`` verdicts, so a consumer
    can tell how old the ground truth is.
    """
    return json.loads(_read())


def cases(*, accepted_only: bool = False) -> list[dict]:
    """The conformance cases, in corpus order.

    ``accepted_only`` keeps just those Isabelle accepts — the ones with a
    ground truth to conform *to*. Pass it unless you specifically want
    bug-for-bug agreement on input a build would refuse.
    """
    out = load()["cases"]
    return [c for c in out if c["isabelle"] == "accepts"] if accepted_only else out


def session_names(case: dict) -> list[str]:
    """The session names a case expects, in declaration order.

    Derived from ``case["expect"]`` rather than stored separately, so the two
    cannot drift apart. This is the whole of what a name-only reader needs.
    """
    return [s["name"] for s in case["expect"]]


def path() -> Path:
    """Filesystem path of the corpus, for a consumer that would rather read
    the JSON itself than import anything.

    Raises :class:`FileNotFoundError` if this installation has no real file to
    point at — a zip import, or any loader that is not the filesystem one.
    Use :func:`load` there, which works either way.

    Note what this does *not* do.  The obvious implementation is
    ``with resources.as_file(...) as p: return Path(p)``, and it is wrong in
    exactly the case this function exists to handle: for a non-filesystem
    loader ``as_file`` extracts to a temporary file and **deletes it when the
    context exits**, so the returned path would name a file that no longer
    exists.  The caller then gets a `Path` that fails on open, at some
    distance from the cause.  Failing here, with a reason, is the whole value
    of having a separate accessor rather than exposing the Traversable.
    """
    from importlib import resources
    resource = resources.files(DATA_PACKAGE) / DATA_NAME
    if isinstance(resource, Path) and resource.is_file():
        return resource
    raise FileNotFoundError(
        f"{DATA_PACKAGE}/{DATA_NAME} is not a real file on this installation "
        f"({type(resource).__name__}); use isabelle_layout.conformance.load()")
