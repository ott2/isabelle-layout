"""This package must agree with the corpus it ships.

The corpus exists so that *other* readers can prove they agree with this one.
That is worthless if this one has drifted from it, so the first consumer of
the shipped artefact is the package itself — and it reads the artefact through
the installed-package loader, not off the source tree, because a corpus that
is correct in the repository and missing from the wheel is a corpus no
consumer can use.  That failure is invisible to a `PYTHONPATH=src` suite.

Every case was put to `isabelle sessions -d` (Isabelle2025-2) when it was
generated; `scripts/build_conformance.py` regenerates and re-verifies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from isabelle_layout import conformance, parse_root_sessions

CASES = conformance.cases()
IDS = [c["id"] for c in CASES]


def parse(tmp_path: Path, root_text: str):
    (tmp_path / "ROOT").write_text(root_text)
    return parse_root_sessions(tmp_path / "ROOT")


# ------------------------------------------------------------ the agreement

@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_this_package_matches_its_own_corpus(tmp_path, case):
    sessions = parse(tmp_path, case["root"])
    got = [
        {
            "name": s.name,
            "parent": s.parent,
            "in_subdir": s.in_subdir,
            "used_sessions": list(s.used_sessions),
            "directories": list(s.directories),
            "theories": [[n, o] for n, o in s.theories],
        }
        for s in sessions
    ]
    assert got == case["expect"], case["why"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_session_names_helper_agrees_with_the_full_parse(tmp_path, case):
    # The name-only view is what a reader like `isabelle-watchdog` compares
    # against, so it has to be derived from the same place rather than stored
    # beside it and allowed to drift.
    sessions = parse(tmp_path, case["root"])
    assert [s.name for s in sessions] == conformance.session_names(case)


# --------------------------------------------------------- the corpus itself

def test_the_corpus_ships_inside_the_installed_package():
    """The point of the whole exercise.  If this fails, the file is in the
    repository and not in the wheel, and every consumer's conformance test
    fails on install rather than on a real disagreement."""
    assert conformance.path().is_file()
    assert conformance.path().name == "conformance.json"


def test_the_corpus_records_what_it_was_verified_against():
    # A consumer has to be able to tell how old the ground truth is.
    data = conformance.load()
    assert data["schema"] == 1
    assert data["verified_against"].startswith("Isabelle")


def test_both_kinds_of_case_are_present_and_labelled():
    """Cases split into "Isabelle accepts this" and "Isabelle rejects this".

    Conflating them is the specific error this corpus corrects: two of the
    eight cases it was seeded with were presented as verified Isabelle
    behaviour when `isabelle build` in fact refuses them outright.
    """
    verdicts = {c["isabelle"] for c in CASES}
    assert verdicts == {"accepts", "rejects"}
    assert len(conformance.cases(accepted_only=True)) < len(CASES)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_every_case_says_why_it_exists(case):
    # A case that cannot say what it would catch is a case nobody maintains,
    # and the first one to fail spuriously gets deleted rather than read.
    assert len(case["why"]) > 40


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["isabelle"] == "rejects"],
    ids=[c["id"] for c in CASES if c["isabelle"] == "rejects"])
def test_the_rejected_cases_carry_isabelles_complaint(case):
    """A "rejects" case is only meaningful with the reason attached — it is
    the evidence that the verdict came from the prover rather than from an
    assumption, and the reasons are not all of one kind.  Three of these are
    syntax errors; `two-sessions-sharing-a-directory` parses perfectly and is
    refused for a *semantic* reason.  Matching on the word "error" would have
    quietly excluded exactly the case that makes the distinction.
    """
    note = case["isabelle_note"]
    assert len(note) > 20
    assert "ROOT" in note  # Isabelle located the complaint in the file


def test_a_rejected_case_may_still_have_been_parsed_correctly():
    """`rejects` means `isabelle build` refuses the file — NOT that a reader
    which parsed it got the wrong answer.  Blurring those would make the
    corpus unusable for the robustness half of its job."""
    case = next(c for c in CASES if c["id"] == "two-sessions-sharing-a-directory")
    assert case["isabelle"] == "rejects"
    assert conformance.session_names(case) == ["A", "B"]  # the correct parse


# ------------------------------------------------- the defects it was born of

@pytest.mark.parametrize("case_id, expected", [
    # A quoted name may contain `.` and `-`; truncating at either silently
    # renames the session to a different, existing one.
    ("quoted-name-with-dots-and-hyphens", ["With.Dots-2"]),
    # Isabelle rejects this spelling, but readers must still not disagree
    # about it: one built `Probe (AFP)` while another recorded `Probe`.
    ("quoted-name-with-spaces", ["Probe (AFP)"]),
    ("bare-name-with-dots-and-hyphens", ["With.Dots-2"]),
])
def test_the_two_live_defects_stay_fixed(case_id, expected):
    case = next(c for c in CASES if c["id"] == case_id)
    assert conformance.session_names(case) == expected
