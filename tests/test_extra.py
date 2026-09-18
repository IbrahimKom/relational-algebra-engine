"""Coverage beyond the 25 required cases: the operators/paths they don't
each individually exercise, plus a few tokenizer/loader edge cases.
"""

import os
import pytest

from src.errors import NameResolutionError, SchemaError
from tests.helpers import load_env, run, tree, parse

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def employees_env():
    env, _ = load_env(os.path.join(FIXTURES, "employees.ra"))
    return env


def test_rename_changes_identity_not_columns(employees_env):
    result = run(employees_env, "rename[X](Employees)")
    assert result.name == "X"
    assert [a.name for a in result.attrs] == ["EID", "Name", "Age", "DID"]


def test_times_qualifies_both_sides_and_full_cross_product(employees_env):
    result = run(employees_env, "Employees times Dept")
    names = {a.qualified_name for a in result.attrs}
    assert names == {"Employees.EID", "Employees.Name", "Employees.Age",
                      "Employees.DID", "Dept.DID", "Dept.DName"}
    assert len(result.tuples) == 3 * 2  # full cross product, no filter


def test_times_without_rename_on_self_is_ambiguity_error(employees_env):
    with pytest.raises(SchemaError):
        run(employees_env, "Employees times Employees")


def test_intersect_and_union_compatible_relations():
    env, _ = load_env(os.path.join(FIXTURES, "assoc_demo.ra"))
    assert run(env, "A intersect B").tuples == {(2,)}
    assert run(env, "A union B").tuples == {(1,), (2,)}


def test_unqualified_reference_ambiguous_after_join_needs_qualification(employees_env):
    combined = run(employees_env, "Emp join[Emp.DID=Dept.DID] Dept")
    # DID exists as both Emp.DID and Dept.DID now -- can't select on bare "DID"
    with pytest.raises(NameResolutionError):
        run(employees_env, "select[DID='D1'](Emp join[Emp.DID=Dept.DID] Dept)")
    assert len(combined.tuples) == 3  # sanity: the join itself still works


def test_unknown_relation_is_name_error():
    env, _ = load_env(os.path.join(FIXTURES, "employees.ra"))
    with pytest.raises(NameResolutionError):
        run(env, "NoSuchTable")


def test_duplicate_relation_definition_is_schema_error(tmp_path):
    p = tmp_path / "dup.ra"
    p.write_text("R (a) = { 1 }\nR (a) = { 2 }\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        load_env(str(p))


def test_comment_and_blank_lines_in_tuple_block_are_ignored(tmp_path):
    p = tmp_path / "commented.ra"
    p.write_text(
        "// a comment before the relation\n"
        "R (a, b) = {\n"
        "  // a comment inside the block\n"
        "\n"
        "  1, 2\n"
        "\n"
        "  3, 4\n"
        "}\n",
        encoding="utf-8",
    )
    env, _ = load_env(str(p))
    assert env["R"].tuples == {(1, 2), (3, 4)}


def test_duplicate_tuples_collapse_to_one(tmp_path):
    p = tmp_path / "dup_tuples.ra"
    p.write_text("R (a) = {\n  1\n  1\n  2\n}\n", encoding="utf-8")
    env, _ = load_env(str(p))
    assert env["R"].tuples == {(1,), (2,)}


def test_decimal_numbers_are_supported():
    t = tree("select[Price>19.99](R)")
    assert "Num(19.99)" in t


def test_relation_named_like_a_keyword_still_resolves(tmp_path):
    # 'union' used as a relation NAME (not an attribute) -- only valid at
    # Primary position, where a bare IDENT is always a relation reference.
    p = tmp_path / "kwname.ra"
    p.write_text("union (x) = {\n  1\n}\n", encoding="utf-8")
    env, _ = load_env(str(p))
    result = run(env, "union")
    assert result.tuples == {(1,)}
