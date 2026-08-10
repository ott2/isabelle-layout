r"""theories.py — what a `.thy` file's header says, and which files a session owns.

Two questions that turn out to be one.  "What does this theory import" is a
header-parsing problem; "which theories belong to this session" is a
reachability problem — and the second is answered by repeatedly asking the
first, because a session's ROOT routinely declares far fewer theories than the
session builds.  AFP's `AODV` declares **one** theory and builds **73**: the
rest arrive through `imports`.  A tool that reads only the ROOT under-counts
that entry by 99%.

The header parser is anchored on ``theory NAME imports``, not on a bare
``imports``, and that anchoring earns its keep twice over:

  - It stops the clause at ``keywords``/``abbrevs``, which are header clauses
    *following* imports and not imports themselves.  105 AFP theories declare
    a ``keywords`` block, and scanning to ``begin`` swallowed it whole --
    `AutoCorres` "imported" ``keywords``, ``autocorres``, ``::``, ``thy_decl``
    and ``and``.
  - It refuses to match a file with no imports clause at all (``theory Pure
    begin``), where a lone ``imports`` further down the file would otherwise
    pair with some locale's ``begin``.

And it reads the **whole file**, not a fixed head window.  A window is simply
the wrong shape: ``section``/``text`` blocks may legally precede the ``theory``
command, and an AFP title-and-history block routinely pushes the header past
any constant one would pick.  At 50 lines it lost the clause on 62 of the AFP's
9,604 theories -- worst case ``Cook_Levin/Basics.thy``, at line 199.

**On `_classify_import` being private.**  Deciding that ``HOL-Library.FuncSet``
is "infrastructure" and ``Other.Foo`` is "somebody else's entry" is an
*analysis judgement*, not a fact about the file, and this package's boundary is
drawn at what a file says.  It is here because the import closure below cannot
be computed without it -- a walk that followed cross-entry imports would drag
in half the AFP -- but it is not part of the public API.  The evidence for that
line is that no consumer outside `isabelle-query` ever imported it.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._lexer import strip_comments
from .project import default_t_dir
from .roots import (
    SessionInfo,
    _parse_root_theories,
    _resolve_thy_file,
    iter_sessions,
    resolve_session_theory,
)


# The theory header, per Pure's grammar:
#
#     theory NAME imports NAME+ [keywords ...] [abbrevs ...] begin
#
# Anchoring on `theory NAME imports` rather than on a bare `imports` matters
# twice over.  It stops the clause at `keywords`/`abbrevs`, which are part of
# the header and not imports — 105 AFP theories declare a `keywords` block, and
# scanning to `begin` swallowed it whole (`AutoCorres` "imported" `keywords`,
# `autocorres`, `::`, `thy_decl`, `and`).  And it refuses to match a file with
# no imports clause at all (`theory Pure begin`), where a lone `imports`
# further down the file would otherwise pair with some locale's `begin`.
# The optional `%tag` is a document-preparation marker Isar allows after any
# command keyword — `theory %invisible All` (AFP's AODV/All.thy).  Anchoring on
# `theory NAME imports` without allowing it silently loses the whole header:
# AODV declares only `All` in its ROOT, so the 72 theories it imports fell out
# of discovery entirely.
_THY_HEADER_RE = re.compile(
    r'\btheory\b(?:\s*%\s*(?:"[^"\n]*"|[\w\'.]+))*'
    r'\s+(?:"[^"\n]*"|[^\s"]+)\s+imports\b(.*?)'
    r'\b(?:begin|keywords|abbrevs)\b', re.DOTALL)


def parse_thy_imports(thy_path: Path) -> list[str]:
    r"""Return the ordered list of theory names from a .thy file's
    `imports ... begin` clause.

    Handles plain names (`Main`) and quoted qualified names
    (`"HOL-Library.FuncSet"`).  Returns the raw import names; callers
    decide whether each is in-project or external (cross-session) by
    cross-referencing against a session's declared theories.
    Returns [] if the file is missing or has no imports clause.

    The whole file is scanned, not a fixed head window.  A window is the
    wrong shape for this: `section`/`text` blocks may legally precede the
    `theory` command, and an AFP title-and-history block routinely pushes the
    header past any constant one would pick — at 50 lines it lost the clause
    on 62 of the AFP's 9,604 theories (worst: `Cook_Levin/Basics.thy` at line
    199), which is a wrong `deps` answer and, worse, silently drops theories
    from the import closure `session_theories` builds discovery from.

    Comments and cartouches are stripped first, so prose in a leading
    `text \<open>...\<close>` cannot contribute a phantom `imports` or an
    early `begin`.
    """
    if not thy_path.exists():
        return []
    try:
        text = thy_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = _THY_HEADER_RE.search(strip_comments(text))
    if not m:
        return []
    tokens = re.findall(r'"([^"]+)"|(\S+)', m.group(1))
    return [a or b for a, b in tokens]


def iter_thy_files(t_dir: Path | None = None) -> list[Path]:
    """Return the ordered list of .thy files declared by ROOT(s) under t_dir.

    Two layouts are supported transparently:

    * **Single ROOT** (``t_dir/ROOT`` exists): order matches that ROOT's
      `theories` block; each theory is resolved at the session root first,
      then in declared subdirectories.
    * **Multi-ROOT** (no ``t_dir/ROOT``, but ROOTs in subdirectories,
      e.g. ``t_dir/a/ROOT`` and ``t_dir/b/ROOT``): every
      session declared by every ROOT under ``t_dir`` is enumerated (via
      ``iter_sessions``) and its theories resolved against the declaring
      session's directory.  Results are deduplicated by resolved path so
      a theory reached through more than one session appears once.

    Theory names with no matching file on disk are silently skipped
    (mirrors bin/common.sh's get_build_files behaviour, so callers can
    run against partial trees during a refactor).
    """
    if t_dir is None:
        t_dir = default_t_dir()
    out: list[Path] = []
    root_path = t_dir / "ROOT"
    if root_path.exists():
        for name in _parse_root_theories(root_path):
            resolved = _resolve_thy_file(name, t_dir=t_dir)
            if resolved is not None:
                out.append(resolved)
        return out
    # Multi-ROOT: union theories across every session under t_dir.
    seen: set[Path] = set()
    for session in iter_sessions(t_dir):
        for theory_entry in session.theories:
            resolved = resolve_session_theory(session, theory_entry)
            if resolved is not None and resolved not in seen:
                seen.add(resolved)
                out.append(resolved)
    return out


# Isabelle *distribution* session names (and unqualified base theories) — an
# import qualified with one of these, or the bare `Main`/`Pure`/`Complex_Main`,
# names base-library *infrastructure*, not a corpus theory.  Everything else
# that is dot-qualified names another *session* (in an AFP census, another
# entry).  The `HOL` prefix covers the whole `HOL-Library` / `HOL-Analysis` /
# … family without listing each.
_INFRA_ROOTS = frozenset({
    "Pure", "Main", "Complex_Main", "Tools", "Doc",
    "FOL", "FOLP", "ZF", "CTT", "LCF", "CCL", "Cube", "Sequents",
})


def _import_session(name: str) -> "str | None":
    """The session prefix of a dot-qualified theory import
    (``HOL-Library.FuncSet`` -> ``HOL-Library``), or None for a bare,
    unqualified import (``AODV_Basic``, ``Main``).  Isabelle qualifies a
    theory as ``<session>.<theory>`` and neither part contains a dot, so the
    single dot is the split point."""
    raw = name.strip().strip('"')
    return raw.rsplit(".", 1)[0] if "." in raw else None


def _classify_import(name: str, session: SessionInfo,
                     stem_index: "dict[str, Path] | None" = None,
                     importer: "Path | None" = None,
                     ) -> "tuple[str, Path | None]":
    """Classify an ``imports`` target relative to the session that imports it.

    Returns ``(kind, path)`` where ``kind`` is:

    * ``"in_entry"`` — a theory inside the entry's own ROOT directory,
      reached as a *bare* name (``Aodv``), a *self-qualified* name
      (``AODV.Aodv``), or a *relative path* (``"variants/a/Foo"``,
      ``"../../Aodv_Basic"``); ``path`` is the resolved ``.thy``.
    * ``"infra"`` — Isabelle distribution / base library (``Pure``, ``Main``,
      ``Complex_Main``, the ``HOL*`` family, ``FOL``/``ZF``/…), or a bare /
      path import that resolves nowhere in the entry (an external base).
    * ``"cross_entry"`` — a dot-qualified theory in *another* (non-distribution)
      session — in an AFP walk, another entry, which a per-entry census must
      not double-count (AODV's ``AWN.OClosed_Transfer``, from its parent
      session).

    Isabelle addresses a *same-entry* theory three ways (bare, self-qualified,
    or by relative path) and every *cross-session* reference by a
    ``<session>.<theory>`` qualifier — so the name (plus, for a path import,
    the importing file's location) classifies without a prover.  ``stem_index``
    (theory-stem -> path for the entry's directory) resolves bare / qualified
    names in O(1) when supplied; ``importer`` is the importing theory's path,
    used to resolve relative-path imports and confined to the entry's ROOT
    directory so a ``../`` cannot escape into a sibling entry.

    **Private**: the ``infra`` / ``cross_entry`` split is an analysis
    judgement about what counts as infrastructure, not a reading of what a
    file says, and this package's public surface is the latter.  It lives here
    because :func:`session_theories` cannot bound its walk without it.
    """
    raw = name.strip().strip('"')
    entry_root = session.root_path.parent

    if "/" in raw:  # relative-path import (quoted), e.g. "../JVM/JVMExec"
        base_dir = importer.parent if importer is not None else session.session_dir
        cand = (base_dir / f"{raw}.thy").resolve()
        if cand.exists() and entry_root in cand.parents:
            return ("in_entry", cand)
        # Fall back to the leaf theory name within the entry's own tree.
        leaf = Path(raw).name
        q = stem_index.get(leaf) if stem_index is not None else None
        return ("in_entry", q) if q is not None else ("infra", None)

    sess = _import_session(raw)
    if sess is None:  # bare: an in-entry theory, or an unqualified base
        # Resolution decides, and `_INFRA_ROOTS` is deliberately NOT consulted
        # first.  A bare name that resolves to a file the session owns *is*
        # that file, whatever it is called: `src/CCL` is a session named `CCL`
        # whose `Term.thy` imports `CCL`, meaning `CCL/CCL.thy`.  Short-
        # circuiting on the name lost it, and with it everything reachable
        # only through it -- 6 theories across `CCL`, `Cube` and `Sequents`.
        # The name list still governs *qualified* imports below, where there
        # is no local file to check against.
        #
        # Safe because owning such a name is rare and unambiguous when it
        # happens: across the AFP and the distribution exactly 12 sessions
        # hold a theory named like a distribution logic, 11 of them the object
        # logic defining itself (`ZF/ZF.thy`), and the twelfth an AFP entry
        # with its own `Sequents.thy`.  Measured over both corpora: the AFP
        # load set is unchanged at 9,910, the distribution gains 6, none lost.
        p = (stem_index.get(raw) if stem_index is not None
             else resolve_session_theory(session, raw))
        return ("in_entry", p) if p is not None else ("infra", None)

    if sess == session.name:  # self-qualified sibling (AODV.Aodv within AODV)
        thy = raw.rsplit(".", 1)[1]
        p = (stem_index.get(thy) if stem_index is not None
             else resolve_session_theory(session, thy))
        return ("in_entry", p) if p is not None else ("infra", None)
    if sess in _INFRA_ROOTS or sess.startswith("HOL"):
        return ("infra", None)
    return ("cross_entry", None)


def _theory_search_roots(session: SessionInfo) -> list[Path]:
    """The directories a session's theory files may live in.

    The session directory, plus every `directories` entry that lands *outside*
    it.  Entries inside it are already covered, because the session directory
    is scanned recursively; adding them would mean re-walking a tree to learn
    nothing.

    The clause is not decoration.  `HOL-ODE-Numerics` declares
    ``in "Numerics"`` and ``directories "../Refinement"``, and indexing only
    the session directory left its bare imports into `../Refinement`
    unresolvable — see `[session-dirs]`.  Six such entries exist across the
    AFP and the distribution (three sessions); the other 147 `directories`
    entries stay inside the session directory, which is why this went
    unnoticed.

    Order matches :func:`~isabelle_layout.roots.resolve_session_theory`: the
    session directory first, then each declared directory in declaration
    order, so the two agree about which file a name resolves to when more than
    one matches.
    """
    base = session.session_dir
    roots = [base]
    resolved_base = base.resolve()
    for d in session.directories:
        target = (base / d).resolve()
        if resolved_base not in (target, *target.parents):
            roots.append(target)
    return roots


def session_theories(session: SessionInfo, *,
                     follow_imports: bool = True,
                     ) -> list[tuple[str, Path]]:
    """The ``(name, path)`` theories that belong to a session.

    Always includes the theories declared in the session's ROOT ``theories``
    block (resolved via :func:`~isabelle_layout.roots.resolve_session_theory`).
    When ``follow_imports`` (the default), also includes the transitive closure
    of their **in-entry** imports — bare-name imports that resolve to a ``.thy``
    in one of the session's own directories, meaning the session directory and
    anything the ROOT's ``directories`` clause adds to it — so a session that
    declares a few leaf theories and pulls the rest in via ``imports`` (common
    in the AFP: ``AODV`` declares 1, builds 73) is counted in full.

    Cross-entry (dot-qualified, another session) and infrastructure
    (``HOL*``/``Pure``/…) imports are **not** followed: over the whole AFP
    each entry then contributes its own theories exactly once, with no
    double-counting of shared dependency entries or the base library.

    Import-reachability, not a bare ``*.thy`` glob, bounds the set — so
    orphan / scratch / WIP theories that no declared root imports are
    excluded, matching what ``isabelle build`` actually compiles.  BFS order
    from the declared roots; deduplicated by resolved path.
    """
    stem_index: dict[str, Path] = {}
    if follow_imports:
        # One directory scan → O(1) in-entry resolution for every bare import.
        for scan_root in _theory_search_roots(session):
            if not scan_root.is_dir():
                continue
            for p in scan_root.rglob("*.thy"):
                stem_index.setdefault(p.stem, p)

    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    frontier: list[Path] = []
    for entry in session.theories:
        p = resolve_session_theory(session, entry)
        if p is None:
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append((entry[0], p))
        frontier.append(p)

    if follow_imports:
        while frontier:
            p = frontier.pop()
            for imp in parse_thy_imports(p):
                kind, q = _classify_import(imp, session, stem_index, importer=p)
                if kind != "in_entry" or q is None:
                    continue
                rq = q.resolve()
                if rq in seen:
                    continue
                seen.add(rq)
                out.append((q.stem, q))
                frontier.append(q)
    return out
