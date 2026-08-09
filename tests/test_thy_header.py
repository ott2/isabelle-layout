r"""`parse_thy_imports` reads the whole theory header, and only the header.

Regression for `[thy-header]`.  The clause was once found by regex-searching the
first 50 lines for `imports ... begin`, which failed three ways:

* **the window** — `section`/`text` blocks may legally precede the `theory`
  command, and an AFP title-and-history block routinely pushes the header past
  any constant.  62 of the AFP's 9,604 theories lost their imports entirely
  (worst: `Cook_Levin/Basics.thy`, line 199), which is a wrong `deps` answer
  *and* a silent hole in the discovery closure `session_theories` builds.
* **the terminator** — `keywords` and `abbrevs` are header clauses that follow
  `imports`, so scanning to `begin` swallowed them.  105 AFP theories declare
  a `keywords` block; `AutoCorres` "imported" `keywords`, `autocorres`, `::`
  and `thy_decl`.
* **nested comments** — Isabelle's `(* *)` nest, and a non-greedy regex stops
  at the first `*)`.  `Universal_Turing_Machine.GeneratedCode` reported an
  import literally named `*)`.

Verified against Isabelle's own `theory/parents` export over 11 built
sessions: 563/563 theories agree.
"""

from __future__ import annotations

import pytest

from isabelle_layout import parse_thy_imports
from isabelle_layout import _lexer


@pytest.fixture
def imports_of(tmp_path):
    """Write a theory snippet and return its parsed imports."""
    def _imports(text: str) -> list:
        p = tmp_path / "T.thy"
        p.write_text(text, encoding="utf-8")
        return parse_thy_imports(p)
    return _imports


# --- the window ------------------------------------------------------------

def test_header_past_a_long_preamble_is_found(imports_of):
    # 80 lines of title block, as `Cook_Levin/Basics.thy` carries.
    preamble = "(*\n" + "\n".join(f"   line {i}" for i in range(80)) + "\n*)\n"
    assert imports_of(preamble + 'theory T\n  imports Bar\nbegin\nend\n') == ["Bar"]


def test_section_and_text_may_precede_the_theory_command(imports_of):
    pre = ('section \\<open>Title\\<close>\n'
           'text \\<open>' + "prose\n" * 60 + '\\<close>\n')
    assert imports_of(pre + 'theory T\n  imports Bar\nbegin\nend\n') == ["Bar"]


def test_prose_before_the_header_cannot_supply_a_phantom_clause(imports_of):
    # The words are inside a cartouche, so they are not syntax.
    pre = 'text \\<open>we import Baz here: imports Baz begin\\<close>\n'
    assert imports_of(pre + 'theory T\n  imports Bar\nbegin\nend\n') == ["Bar"]


# --- the terminator --------------------------------------------------------

def test_keywords_block_is_not_imported(imports_of):
    assert imports_of(
        'theory T\n  imports Main\n'
        '  keywords "autocorres" :: thy_decl and "declare_prototype"'
        ' :: thy_goal_stmt\nbegin\nend\n') == ["Main"]


def test_abbrevs_block_is_not_imported(imports_of):
    assert imports_of(
        'theory T\n  imports Main Other\n'
        '  abbrevs "===" = "\\<equiv>"\nbegin\nend\n') == ["Main", "Other"]


# --- comments --------------------------------------------------------------

def test_nested_comment_in_the_clause(imports_of):
    assert imports_of(
        'theory T\n'
        '  imports A\n'
        '(*        "HOL-Library.Skip" (* see codegen.pdf *) *)\n'
        '          "HOL-Library.Code_Binary_Nat" (* keep *)\n'
        'begin\nend\n') == ["A", "HOL-Library.Code_Binary_Nat"]


def test_comment_between_tokens_still_separates_them(imports_of):
    assert imports_of('theory T imports A(* c *)B begin\nend\n') == ["A", "B"]


# --- shapes that must survive ----------------------------------------------

def test_quoted_qualified_name(imports_of):
    assert imports_of('theory T\n  imports "HOL-Library.FuncSet"\n'
                      'begin\nend\n') == ["HOL-Library.FuncSet"]


def test_relative_path_import(imports_of):
    # FSM_Tests writes `imports "../FSM"`; the token must survive whole.
    assert imports_of('theory T\nimports "../FSM"\nbegin\nend\n') == ["../FSM"]


def test_order_is_preserved(imports_of):
    assert imports_of('theory T\n  imports C A B\nbegin\nend\n') == ["C", "A", "B"]


def test_one_line_header(imports_of):
    assert imports_of('theory T imports Main begin\nend\n') == ["Main"]


@pytest.mark.parametrize("header", [
    # `theory %invisible All` — Isar allows a `%tag` after any command keyword.
    # AFP's AODV/All.thy uses it, and since AODV's ROOT declares only `All`,
    # missing the tag dropped 72 theories out of discovery.
    'theory %invisible T\n',
    'theory % invisible T\n',
    'theory %"vis" T\n',
])
def test_document_tag_after_the_command_keyword(imports_of, header):
    assert imports_of(header + 'imports Bar\nbegin\nend\n') == ["Bar"]


# --- no clause at all ------------------------------------------------------

def test_theory_without_imports_yields_nothing(imports_of):
    # `theory Pure begin`.  A bare `imports` further down (here inside a
    # locale) must not pair with some later `begin`.
    assert imports_of(
        'theory T begin\n'
        'locale L begin\n'
        'text \\<open>imports\\<close>\n'
        'end\nend\n') == []


def test_missing_file_yields_nothing(tmp_path):
    assert parse_thy_imports(tmp_path / "absent.thy") == []


# --- the lexer, in isolation -----------------------------------------------

class TestStripBlockComments:
    """The nesting-aware stripper."""

    def test_nested_pair_is_removed_whole(self):
        assert _lexer.strip_block_comments("a (* x (* y *) z *) b").split() \
            == ["a", "b"]

    def test_stray_closer_is_left_alone(self):
        assert _lexer.strip_block_comments("a *) b") == "a *) b"

    def test_unterminated_comment_swallows_the_rest(self):
        assert _lexer.strip_block_comments("a (* b").strip() == "a"

    def test_text_without_comments_is_returned_unchanged(self):
        # Identity, not equality: the no-comment fast path must not copy.
        # It runs over every `.thy` in a corpus, and most have no comment in
        # the header region at all.
        text = "plain text"
        assert _lexer.strip_block_comments(text) is text

    def test_two_separate_comments(self):
        assert _lexer.strip_block_comments("a (* x *) b (* y *) c").split() \
            == ["a", "b", "c"]


class TestStripCartouches:
    """The token-driven rewrite must match the old per-character walk."""

    @staticmethod
    def reference(text: str) -> str:
        out, i, depth = [], 0, 0
        while i < len(text):
            if text.startswith(r"\<open>", i):
                depth += 1
                i += len(r"\<open>")
            elif text.startswith(r"\<close>", i):
                depth = max(0, depth - 1)
                i += len(r"\<close>")
            else:
                if depth == 0:
                    out.append(text[i])
                i += 1
        return "".join(out)

    @pytest.mark.parametrize("text", [
        r"a \<open>b\<close> c",
        r"a \<open>b \<open>n\<close> d\<close> e",
        r"a \<close> b",                      # stray closer
        r"a \<open>b",                        # unterminated
        "no cartouches here",
        r"\<open>\<close>",
    ])
    def test_matches_the_reference_walk(self, text):
        assert _lexer.strip_cartouches(text) == self.reference(text)
