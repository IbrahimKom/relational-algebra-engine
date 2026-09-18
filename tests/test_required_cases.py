"""The 25 required test cases from assignment Section 7, numbered to match.
Each test's docstring/id is the case number so a failure is easy to map
back to the spec table.
"""

import os
import pytest

from src.errors import LexError, ParseError, NameResolutionError, SchemaError, TypeCheckError
from tests.helpers import tree, parse, load_env, run

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ------------------------------------------------------------ 7.1 Tokenizer

def test_case1_no_whitespace_parses():
    assert tree("select[x1=3](R)") == (
        "Select(cond=Eq(Attr(x1), Num(3)))\n"
        "└── Relation(R)"
    )


def test_case2_matches_case1():
    assert tree("select[x1=3](R)") == tree("select[ x1 = 3 ](R)")


def test_case3_single_ge_token():
    assert "Ge(Attr(Age), Num(30))" in tree("select[Age>=30](R)")


def test_case4_gt_then_negative_number_no_gt_minus_glitch():
    t = tree("select[Age>-30](R)")
    assert "Gt(Attr(Age), Num(-30))" in t


def test_case5_paren_inside_string():
    t = tree("select[Name='Bob)'](R)")
    assert "Str('Bob)')" in t


def test_case6_comma_inside_string():
    t = tree("select[Name='a,b'](R)")
    assert "Str('a,b')" in t


def test_case7_doubled_quote_is_one_literal_quote():
    t = tree("select[Name='O''Brien'](R)")
    assert "Str(\"O'Brien\")" in t


def test_case8_keyword_spelled_attribute():
    t = tree("select[union=3](R)")
    assert "Eq(Attr(union), Num(3))" in t


def test_case9_unterminated_string_is_lex_error_with_position():
    with pytest.raises(LexError) as exc:
        parse("select[Name='Bob](R)")
    assert exc.value.line == 1
    assert exc.value.col is not None


# --------------------------------------------------------- 7.2 Grammar/prec

def test_case10_union_then_minus_groups_left_per_grammar():
    t = tree("A union B minus C")
    assert t == (
        "Minus\n"
        "├── Union\n"
        "│   ├── Relation(A)\n"
        "│   └── Relation(B)\n"
        "└── Relation(C)"
    )


def test_case11_minus_minus_is_left_associative():
    t = tree("A minus B minus C")
    assert t == (
        "Minus\n"
        "├── Minus\n"
        "│   ├── Relation(A)\n"
        "│   └── Relation(B)\n"
        "└── Relation(C)"
    )


def test_case11_data_instance_where_the_other_grouping_differs():
    # A={1,2}, B={2}, C={2}
    env, _ = load_env(os.path.join(FIXTURES, "assoc_demo.ra"))
    left_assoc = run(env, "(A minus B) minus C").tuples   # our documented grouping
    right_assoc = run(env, "A minus (B minus C)").tuples  # the grouping we did NOT pick
    assert left_assoc == {(1,)}
    assert right_assoc == {(1,), (2,)}
    assert left_assoc != right_assoc


def test_case12_not_binds_tighter_than_and_binds_tighter_than_or():
    t = tree("select[not (a=1 and b=2) or c>3](R)")
    assert "Or(Not(And(Eq(Attr(a), Num(1)), Eq(Attr(b), Num(2)))), Gt(Attr(c), Num(3)))" in t


def test_case13_and_binds_tighter_than_or():
    t = tree("select[a=1 and b=2 or c=3](R)")
    assert "Or(And(Eq(Attr(a), Num(1)), Eq(Attr(b), Num(2))), Eq(Attr(c), Num(3)))" in t


def test_case14_three_levels_of_nesting():
    t = tree("project[Name](select[Age>30](select[DID='D1'](Employees)))")
    assert t == (
        "Project(attrs=[Name])\n"
        "└── Select(cond=Gt(Attr(Age), Num(30)))\n"
        "    └── Select(cond=Eq(Attr(DID), Str('D1')))\n"
        "        └── Relation(Employees)"
    )


def test_case15_explicit_parens_override_precedence():
    t = tree("(A union B) minus (C intersect D)")
    assert t.startswith("Minus\n")
    assert "Union" in t and "Intersect" in t


def test_case16_missing_close_paren_is_syntax_error_with_position():
    with pytest.raises(ParseError) as exc:
        parse("select[Age>30](R")
    assert exc.value.line == 1


def test_case17_empty_projection_list_is_syntax_error():
    with pytest.raises(ParseError):
        parse("project[](R)")


# ------------------------------------------------------------- 7.3 Semantics

@pytest.fixture
def employees_env():
    env, _ = load_env(os.path.join(FIXTURES, "employees.ra"))
    return env


def test_case18_attribute_vs_attribute_not_attribute_vs_literal(employees_env):
    result = run(employees_env, "select[Name=Name](Employees)")
    assert len(result.tuples) == 3  # every row: Name always equals itself


def test_case19_qualified_join_keeps_both_did_columns(employees_env):
    result = run(employees_env, "Emp join[Emp.DID=Dept.DID] Dept")
    names = {a.qualified_name for a in result.attrs}
    assert "Emp.DID" in names and "Dept.DID" in names
    assert len(result.tuples) == 3


def test_case20_self_join_needs_rename(employees_env):
    result = run(employees_env,
                  "rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp")
    # every employee's manager is E3 (Bob), so E2's side is always Bob
    assert len(result.tuples) == 3
    names = {a.name for a in result.attrs}
    assert names == {"EID", "Name", "Age", "DID", "MgrID"}  # same base names, distinguished by qualifier
    # a bare, unrenamed second Emp would collide -- that's *why* rename is required:
    with pytest.raises(SchemaError):
        run(employees_env, "Emp join[Emp.MgrID=Emp.EID] Emp")


def test_case21_union_of_incompatible_schemas_is_schema_error():
    env, _ = load_env(os.path.join(FIXTURES, "sets.ra"))
    with pytest.raises(SchemaError):
        run(env, "R union S")


def test_case22_comparing_number_to_string_is_type_error(employees_env):
    with pytest.raises(TypeCheckError):
        run(employees_env, "select[Age>'30'](Employees)")


def test_case23_projection_removes_duplicates(employees_env):
    result = run(employees_env, "project[DID](Employees)")
    assert result.tuples == {("D1",), ("D2",)}


def test_case24_duplicate_projected_attribute_is_documented_error(employees_env):
    # Design decision (GRAMMAR.md / README.md): projecting the same
    # attribute twice is a schema error, since the output would need two
    # columns with the identical qualified name.
    with pytest.raises(SchemaError):
        run(employees_env, "project[Name, Name](Employees)")


def test_case25_empty_result_prints_schema_cleanly(employees_env):
    result = run(employees_env, "select[Age>999](Employees)")
    assert result.tuples == set()
    assert [a.name for a in result.attrs] == ["EID", "Name", "Age", "DID"]
