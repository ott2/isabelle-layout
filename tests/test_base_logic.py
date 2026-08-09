"""`resolve_base_logic` / `is_hol_base`: classify a session's object logic by
**chain-resolving** its ROOT parent to a distribution root.

The chain is the point: the AFP's ZF cluster sits two+ hops from its
`ZF-Constructible` base (`Independence_CH` → `Transitive_Models` → … ), which an
immediate-parent test misclassifies as HOL.

Note the import lines.  `resolve_base_logic` is structural — it follows what
ROOTs declare — so it is top-level API.  `is_hol_base` is a fact about the
Isabelle distribution's names, so it comes from `isabelle_layout.distribution`.
The split is the [distribution-module] decision, and these two lines are what
it looks like at a call site.
"""

from __future__ import annotations

import pytest

from isabelle_layout import resolve_base_logic
from isabelle_layout.distribution import is_hol_base, is_known_nonhol_base


# A HOL entry; a HOL entry parented on another AFP session; the ZF cluster
# (transitive); a direct ZF entry; a Pure entry.
PARENTS = {
    "Alpha": "HOL",
    "Beta": "Collections",          # AFP HOL session ...
    "Collections": "HOL-Library",   # ... which itself roots at HOL
    "Forcing": "ZF-Constructible",
    "Independence_CH": "Transitive_Models",
    "Transitive_Models": "Delta_System_Lemma",
    "Delta_System_Lemma": "ZF-Constructible",
    "Recursion-Addition": "ZF",
    "SpecCheck": "Pure",
}


@pytest.mark.parametrize("session, base", [
    ("Alpha", "HOL"),
    ("Recursion-Addition", "ZF"),
    ("SpecCheck", "Pure"),
])
def test_direct_parent_is_a_distribution_root(session, base):
    assert resolve_base_logic(session, PARENTS) == base


@pytest.mark.parametrize("session, base", [
    # The exact case an immediate-parent test gets wrong.
    ("Independence_CH", "ZF-Constructible"),
    ("Forcing", "ZF-Constructible"),
    # An AFP-parented HOL entry still resolves to HOL (no false non-HOL).
    ("Beta", "HOL-Library"),
])
def test_transitive_chain_reaches_the_root(session, base):
    assert resolve_base_logic(session, PARENTS) == base


def test_cycle_is_guarded():
    assert resolve_base_logic("a", {"a": "b", "b": "a"}) == "b"


def test_unknown_session_is_its_own_base():
    # Nothing to follow: a name absent from the map is already a root.
    assert resolve_base_logic("HOL-Analysis", PARENTS) == "HOL-Analysis"


@pytest.mark.parametrize("base", ["HOL", "HOL-Library", "HOL-Analysis", "HOL-ZF"])
def test_hol_family_allowlisted(base):
    assert is_hol_base(base)


@pytest.mark.parametrize("base",
                         ["Pure", "ZF", "ZF-Constructible", "FOL", "CTT", "Sequents"])
def test_other_object_logics_are_non_hol(base):
    assert not is_hol_base(base)


def test_the_two_predicates_default_in_opposite_directions():
    """Not negations of each other, on purpose.

    An unrecognised base — an out-of-scope parent *session* name rather than a
    distribution logic — must be non-HOL to `is_hol_base` (which gates a
    HOL-only table and must never mis-apply) and *not* positively non-HOL to
    `is_known_nonhol_base` (which gates an opt-out from a HOL default).
    Swapping them silently inverts what happens to every base nobody has heard
    of, which is the case that actually arises.
    """
    unknown = "Multitape_TM_Substrate"
    assert not is_hol_base(unknown)
    assert not is_known_nonhol_base(unknown)
