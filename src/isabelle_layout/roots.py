r"""roots.py — what a ROOT file declares.

A ROOT is Isabelle's build manifest, and reading one is harder than it looks
for a reason that has nothing to do with the grammar: the file is mostly
*prose*.  Descriptions, chapter headings, commented-out sessions and
cartouche-wrapped explanations sit in the same file as the declarations, and a
line-oriented reader cannot tell them apart.  So this module tokenises rather
than matches, over text the lexer has already cleaned (see `_lexer`).

What the tokeniser buys, concretely:

  - ``session "Probe (AFP)"`` is one session whose name contains a space and
    parentheses, not a session ``Probe``.
  - ``session With.Dots-2`` is one name, not ``With``.  Isabelle session names
    admit ``.`` and ``-``; ``HOL-Analysis`` truncated at the hyphen is a
    different, real session.
  - ``(* session Retired = HOL + *)`` declares nothing.
  - ``description \<open>session Ghost = X\<close>`` declares nothing.
  - ``theory Main (global)`` declares a theory ``Main``, not also a theory
    ``global``: bracketed and parenthesised groups are skipped wholesale,
    because they hold options and annotations rather than names.

The first two of those were live defects in a hand-rolled parser measured
against this one, and they are the reason the conformance corpus exists.

**Scope discipline.**  `discover_roots` follows a ``ROOTS`` index when there is
one, exactly as ``isabelle build -D`` does, so scan scope equals build scope.
A bare recursive glob silently widens scope to ROOT files the build never
compiles -- a sibling session deliberately omitted from ``ROOTS`` is omitted
here too.

**Deprecation, reconsidered.**  Three functions here carried a ``DEPRECATED``
banner in `isabelle_query.common`, on the stated reasoning that "no in-repo
callers remain".  That reasoning was scoped to the *query tool*: the callers
were in the `bin/` tooling, which is to say outside the repository that
declared them dead.  In a library those callers are the point.  They are
therefore not deprecated here -- they are **private**
(`_parse_root_theories`, `_parse_root_directories`, `_resolve_thy_file`),
because no consumer imports them directly and `iter_thy_files`, which four
consumers do import, is built out of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ._lexer import strip_comments
from .project import default_t_dir, read_text_bounded


# Keywords that terminate a `theories` or `directories` block in a ROOT
# file (i.e. names of sibling clauses at the same nesting level).
# A ROOT is a declaration file, not a document.  The largest in the AFP and
# the Isabelle distribution together is the distribution's own `HOL/ROOT` at
# 30 KB, so this is a thirty-fold margin — wide enough that no real ROOT can
# reach it, narrow enough that a hostile one cannot be read into memory
# unbounded.  The same cap covers the `ROOTS` index, which is a list of
# directory names and smaller still.
_MAX_ROOT_BYTES = 1024 * 1024

_ROOT_BLOCK_TERMINATORS = (
    "theories", "document_files", "document_theories",
    "sessions", "options", "description", "chapter", "session",
    "directories",
)


def _is_terminator(stripped: str, *, exclude: str) -> bool:
    """True iff `stripped` starts with one of the ROOT block terminators
    other than `exclude` (the block we're currently parsing).

    Supports the line-oriented single-ROOT parsers
    (:func:`_parse_root_theories`, :func:`_parse_root_directories`)."""
    for kw in _ROOT_BLOCK_TERMINATORS:
        if kw == exclude:
            continue
        if re.match(rf"{kw}\b", stripped):
            return True
    return False


def _parse_root_theories(root_path: Path) -> list[str]:
    """Return the ordered list of theory names from ROOT's `theories`
    block.  Returns [] if the file doesn't exist or has no block.

    Line-oriented and single-session: it reads the *first* session's
    `theories` block as though it were the file's.  For anything with more
    than one session, or with a comment in an awkward place, use
    :func:`parse_root_sessions`.  Retained because :func:`iter_thy_files`
    is defined in terms of it and preserves its ordering.
    """
    if not root_path.exists():
        return []
    theories: list[str] = []
    in_theories = False
    for line in read_text_bounded(root_path, _MAX_ROOT_BYTES).splitlines():
        stripped = line.strip()
        if re.match(r"theories\b", stripped):
            in_theories = True
            continue
        if _is_terminator(stripped, exclude="theories"):
            in_theories = False
            continue
        # Theory entries are bare identifiers (one per line).  Skip
        # blank lines, comments, and option-decorated forms ("Foo (in
        # Bar)").
        if in_theories and re.match(r"[A-Za-z_][A-Za-z0-9_]*$", stripped):
            theories.append(stripped)
    return theories


def _parse_root_directories(root_path: Path) -> list[str]:
    """Return the ordered list of subdirectory names from ROOT's
    `directories` clause.  Each clause entry is a quoted token; this
    accepts both single-line (`directories "a" "b"`) and multi-line
    forms.  Returns [] if absent.

    Line-oriented and single-session, as :func:`_parse_root_theories` is, and
    retained for the same reason: :func:`_resolve_thy_file` is defined in
    terms of it.
    """
    if not root_path.exists():
        return []
    subdirs: list[str] = []
    in_dirs = False
    for line in read_text_bounded(root_path, _MAX_ROOT_BYTES).splitlines():
        stripped = line.strip()
        if stripped.startswith("directories"):
            in_dirs = True
            stripped = stripped[len("directories"):].strip()
        elif _is_terminator(stripped, exclude="directories"):
            in_dirs = False
            continue
        if in_dirs:
            # Pull every quoted token off the line.
            rest = stripped
            while '"' in rest:
                a = rest.index('"')
                try:
                    b = rest.index('"', a + 1)
                except ValueError:
                    break
                name = rest[a + 1:b]
                if name:
                    subdirs.append(name)
                rest = rest[b + 1:]
    return subdirs


def _resolve_thy_file(name: str, t_dir: Path | None = None) -> Path | None:
    """Resolve a declared theory `name` to its .thy file on disk.

    Searches the session root first, then each subdirectory declared
    under ROOT's `directories` clause.  Returns None if not found.
    ``t_dir`` defaults to :func:`~isabelle_layout.project.default_t_dir`.

    The single-ROOT counterpart of :func:`resolve_session_theory`, which is
    the one to reach for: it honours per-session `in` clauses and per-theory
    overrides, neither of which a single-ROOT view can see.
    """
    if t_dir is None:
        t_dir = default_t_dir()
    candidate = t_dir / f"{name}.thy"
    if candidate.exists():
        return candidate
    root_path = t_dir / "ROOT"
    for sub in _parse_root_directories(root_path):
        candidate = t_dir / sub / f"{name}.thy"
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Multi-root / multi-session API
# ---------------------------------------------------------------------------

@dataclass
class SessionInfo:
    """One session declaration parsed from a ROOT file.

    A ROOT may declare multiple sessions; each is captured separately
    so tools can enumerate theories and follow cross-session references
    accurately (e.g. resolving a theory that lives under the session's
    `in <subdir>` clause rather than alongside the ROOT file).

    Public, and a compatibility surface forever  [session-info]
    ----------------------------------------------------------

    Four of the ten public functions take or return this, so it could not
    have been private without making most of the API unusable — a type you
    cannot name is a type you cannot annotate, store, or write a helper
    around.  Declaring it public is therefore recognising a fact rather than
    granting a privilege, and the useful question is not *whether* it is
    public but *what about it* is promised.

    **Promised:**

    * Read access to these attributes, under these names, with these types:
      ``name: str``, ``root_path: Path``, ``in_subdir: str | None``,
      ``parent: str | None``, ``used_sessions: list[str]``,
      ``directories: list[str]``, ``theories: list[tuple[str, str | None]]``.
    * The ``session_dir`` property.
    * Construction **by keyword**.  New attributes, if any are ever added,
      arrive with defaults and are appended, so existing keyword construction
      keeps working untouched.

    **Not promised**, and deliberately so:

    * That it is a ``dataclass``.  Guaranteeing that would silently pin
      ``asdict``, ``replace``, ``fields()`` and their orderings as API.
    * Equality, ordering, hashing, or ``repr`` — they are whatever the
      implementation currently gives.  Two ``SessionInfo`` values comparing
      equal is not a statement that they name the same session; compare
      ``(name, root_path)`` if that is the question.
    * Field *order*.  The names are the contract.
    * Mutability.  The parser mutates instances while building them; a
      consumer that does so is on its own.

    The reason for drawing it there: the *names* are what consumers read and
    what the ROOT file itself justifies, while order, equality and dataclass
    machinery are incidental to how it happens to be built today.  Promising
    the incidental parts is how a data holder becomes unchangeable.
    """
    name: str
    root_path: Path             # absolute path of the declaring ROOT file
    in_subdir: str | None       # `in <subdir>` clause; None = same dir as ROOT
    parent: str | None          # session name after `=` (heap inherited from)
    used_sessions: list[str] = field(default_factory=list)
        # `sessions` clause: cross-session deps without heap inheritance
    directories: list[str] = field(default_factory=list)
        # `directories` clause: extra subdirs to search for theory files
    theories: list[tuple[str, str | None]] = field(default_factory=list)
        # `theories` clause: list of (name, dir_override).
        #
        # dir_override is **always None** as parsed.  Isabelle's ROOT grammar
        # has no per-theory `in` clause -- `theory_entry = theory_name ~
        # opt_keyword(GLOBAL)` (src/Pure/Build/sessions.scala) -- so a theory
        # in a subdirectory is written as a path (`"sub/Deep"`) or reached via
        # `directories`.  The slot survives because it is public shape and
        # `resolve_session_theory` still honours it for callers that construct
        # entries themselves.

    @property
    def session_dir(self) -> Path:
        """Directory containing this session's .thy files."""
        if self.in_subdir:
            return self.root_path.parent / self.in_subdir
        return self.root_path.parent


# ROOT tokeniser.  Hoisted from `bin/afp-metrics.py` (which had the
# more robust parser) and extended to capture session header context
# (parent, session-level `in <subdir>`) the metrics tool didn't need.

# Keywords recognised by the ROOT tokeniser.  Encountering one closes
# the previous stanza and opens a new one.
_ROOT_KEYWORDS = {
    "chapter", "session", "options", "sessions", "directories",
    "theories", "document_files", "document_theories",
    "export_files", "export_classpath", "global",
    "description", "in",
}

_ID_RE = re.compile(r"[A-Za-z0-9_./\-]+")


def _tokenize_root(text: str):
    """Yield (kind, value) tokens from a ROOT file source.

    kind ∈ {"kw", "id", "str"}.  Both `[...]` and `(...)` are skipped
    wholesale — they hold options (`[document = false]`,
    `(slow very_slow)`) and theory annotations (`Main (global)`) that
    shouldn't leak their internal identifiers into the token stream.
    `=` and `+` are dropped (structural session-header punctuation).
    """
    text = strip_comments(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                return
            yield ("str", text[i + 1:j])
            i = j + 1
            continue
        if c in "[(":
            close = "]" if c == "[" else ")"
            opener = c
            depth = 1
            j = i + 1
            while j < n and depth:
                if text[j] == opener:
                    depth += 1
                elif text[j] == close:
                    depth -= 1
                j += 1
            i = j
            continue
        if c in "=+)]":
            i += 1
            continue
        m = _ID_RE.match(text, i)
        if not m:
            i += 1
            continue
        tok = m.group()
        i = m.end()
        yield ("kw" if tok in _ROOT_KEYWORDS else "id", tok)


def parse_root_sessions(root_path: Path) -> list[SessionInfo]:
    """Parse every `session ...` declaration from a ROOT file.

    Returns sessions in declaration order.  Empty if the file is
    missing or declares no sessions (e.g. `afp/thys/ROOT`, which is
    a `chapter_definition` file).

    The parser handles:

    * Session-level `in <subdir>` and parent (after `=`).
    * Path-valued theory names (`theories "sub/Deep"`), which is how
      Isabelle addresses a theory in a subdirectory — there is no
      per-theory `in` clause in the ROOT grammar.
    * `(...)`-wrapped options (`session NAME (timing)`,
      `theory Main (global)`) — content inside parens is dropped
      wholesale, so `(global)` doesn't spawn a phantom `global`
      theory name.
    * `(* comments *)`, `\\<open>...\\<close>` cartouches, and
      `{* legacy descriptions *}` — all stripped before tokenising,
      so a session declaration inside a comment isn't mis-parsed
      as real syntax.
    """
    if not root_path.exists():
        return []
    text = read_text_bounded(root_path, _MAX_ROOT_BYTES)
    toks = list(_tokenize_root(text))
    out: list[SessionInfo] = []
    abs_root = root_path.resolve()

    cur: SessionInfo | None = None
    state: str | None = None
    pending_theory: tuple[str, str | None] | None = None

    def flush_pending() -> None:
        nonlocal pending_theory
        if pending_theory is not None and cur is not None:
            cur.theories.append(pending_theory)
            pending_theory = None

    i = 0
    while i < len(toks):
        kind, val = toks[i]
        if kind == "kw":
            flush_pending()
            if val == "session":
                if cur is not None:
                    out.append(cur)
                # New session: next id/str is its name.
                cur = SessionInfo(
                    name="<anon>", root_path=abs_root,
                    in_subdir=None, parent=None)
                if i + 1 < len(toks) and toks[i + 1][0] in ("id", "str"):
                    cur.name = toks[i + 1][1]
                    i += 2
                else:
                    i += 1
                state = "session_header"
                continue
            if val == "in":
                # Session-level only: `session NAME in DIR = PARENT`.  Isabelle
                # has no per-theory `in` clause (see the class docstring), so
                # an `in` anywhere else is not a subdirectory override and is
                # skipped rather than guessed at.
                target_arg = (i + 1 < len(toks)
                              and toks[i + 1][0] in ("id", "str"))
                if state == "session_header" and target_arg and cur is not None:
                    cur.in_subdir = toks[i + 1][1]
                    i += 2
                    continue
                i += 1
                continue
            # Any other keyword changes the active stanza.
            state = val
            i += 1
            continue
        # id / str token
        if cur is not None:
            if state == "session_header":
                # First id/str after `session NAME [in DIR]?` is parent.
                cur.parent = val
                state = None
            elif state == "theories":
                flush_pending()
                pending_theory = (val, None)
            elif state == "directories":
                cur.directories.append(val)
            elif state == "sessions":
                cur.used_sessions.append(val)
            # Other states (options, description, ...) — ignore values.
        i += 1
    flush_pending()
    if cur is not None:
        out.append(cur)
    return out


def resolve_session_theory(session: SessionInfo,
                           theory_entry: tuple[str, str | None] | str,
                           ) -> Path | None:
    """Resolve a session-owned theory to its `.thy` file on disk.

    ``theory_entry`` is either a ``(name, dir_override)`` tuple (the
    shape `SessionInfo.theories` produces) or a bare ``name`` string
    (for ad-hoc callers).  Search order:

    1. ``session_dir / dir_override / NAME.thy``  (if dir_override set)
    2. ``session_dir / NAME.thy``
    3. ``session_dir / D / NAME.thy`` for each ``D`` in
       ``session.directories``
    4. ``rglob("NAME.thy")`` under ``session_dir`` — last-resort
       fallback for unusual AFP layouts (only succeeds on a unique
       match).
    """
    if isinstance(theory_entry, tuple):
        name, dir_override = theory_entry
    else:
        name, dir_override = theory_entry, None
    base = session.session_dir
    candidates: list[Path] = []
    if dir_override is not None:
        candidates.append(base / dir_override / f"{name}.thy")
    candidates.append(base / f"{name}.thy")
    for d in session.directories:
        candidates.append(base / d / f"{name}.thy")
    for c in candidates:
        if c.exists():
            return c
    leaf = Path(name).name + ".thy"
    matches = list(base.rglob(leaf))
    return matches[0] if len(matches) == 1 else None


def discover_roots(root_dir: Path) -> list[Path]:
    """Find the ROOT files under `root_dir`, matching `isabelle build -D`.

    When `root_dir` carries an Isabelle `ROOTS` index, descend **only**
    into the subdirectories it lists (one entry per line, relative to the
    index), exactly as `isabelle build -D <root_dir>` does.  This keeps
    scan scope identical to build scope: a sibling session directory
    deliberately omitted from `ROOTS` is excluded here just as the build
    excludes it.  Without this, a bare recursive glob silently widens
    scope to ROOT files the build never compiles.

    When `root_dir` has no `ROOTS` index, fall back to a recursive walk
    (skipping hidden *sub*directories such as `.git`) so single-ROOT and
    ad-hoc layouts still resolve.  Results sorted for stable ordering.
    ROOT files that don't declare any sessions (e.g. AFP's `afp/thys/ROOT`
    chapter-definition file) are still returned — `parse_root_sessions`
    returns [] for them, so they're harmless.
    """
    if not root_dir.exists():
        return []
    out: list[Path] = []
    seen_roots: set[Path] = set()

    def add_root(d: Path) -> None:
        root = d / "ROOT"
        if root.is_file():
            rp = root.resolve()
            if rp not in seen_roots:
                seen_roots.add(rp)
                out.append(rp)

    if not (root_dir / "ROOTS").is_file():
        # No ROOTS index: recursive walk, skipping hidden *sub*directories.
        # The hidden test is judged relative to root_dir, so a hidden ancestor
        # of root_dir — or a `..` in the path as given — does not suppress the
        # whole walk (the old absolute-`parts` test did: a relative root like
        # `../proj` made every "`..`/..." hit look hidden and found nothing).
        for path in sorted(root_dir.rglob("ROOT")):
            if any(part.startswith(".")
                   for part in path.relative_to(root_dir).parts):
                continue
            if path.is_file():
                rp = path.resolve()
                if rp not in seen_roots:
                    seen_roots.add(rp)
                    out.append(rp)
        return sorted(out)

    # ROOTS index present: descend only into listed subdirectories.
    visited_dirs: set[Path] = set()

    def visit(d: Path) -> None:
        rd = d.resolve()
        if rd in visited_dirs:
            return
        visited_dirs.add(rd)
        add_root(d)
        index = d / "ROOTS"
        if index.is_file():
            for line in read_text_bounded(index, _MAX_ROOT_BYTES).splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                sub = d / entry
                if sub.is_dir():
                    visit(sub)

    visit(root_dir)
    return sorted(out)


def iter_sessions(root_dir: Path) -> list[SessionInfo]:
    """Return every session declared by any ROOT under `root_dir`.

    Order: ROOTs in `discover_roots` order; sessions within each
    ROOT in declaration order.
    """
    out: list[SessionInfo] = []
    for root_path in discover_roots(root_dir):
        out.extend(parse_root_sessions(root_path))
    return out


def resolve_base_logic(name: str, parents: dict[str, str]) -> str:
    """Follow `name`'s parent chain in `parents` (session → parent session) to
    its **root** — the first ancestor that is not itself a key, i.e. a
    distribution session not defined in the corpus (`HOL`, `HOL-Analysis`,
    `ZF-Constructible`, `Pure`, …).

    Corpus-wide: `parents` must map every corpus session to its declared parent
    (build it once from `iter_sessions`), so a session two hops from its base
    (`Forcing` → `ZF-Constructible`, `Independence_CH` → `Transitive_Models` →
    … → `ZF-Constructible`) resolves to the *root*, not the immediate parent —
    the classification an immediate-parent test gets wrong.  Cycle-guarded.
    """
    seen: set[str] = set()
    cur = name
    while cur in parents and parents[cur] and parents[cur] not in seen:
        seen.add(cur)
        cur = parents[cur]
    return cur
