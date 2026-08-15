import pytest

from family_camp2.constraints.parser import (
    ConstraintParseError,
    build_constraint_instances,
    parse_expression,
    resolve_target,
)
from family_camp2.constraints.rules import NoActivitiesOnDay, NoActivityBefore, NotOnActivity
from family_camp2.domain import Camper


def camper(name, family="022/Glen", age=10, age_group="Cub"):
    return Camper(name=name, family_id=family, age=age, age_group=age_group)


# --- parse_expression ---


def test_parse_expression_positional_arg():
    name, args, kwargs = parse_expression("no_activities_on_day(2)")
    assert name == "no_activities_on_day"
    assert args == [2]
    assert kwargs == {}


def test_parse_expression_keyword_arg():
    name, args, kwargs = parse_expression('no_activity_before(time="11:00")')
    assert name == "no_activity_before"
    assert args == []
    assert kwargs == {"time": "11:00"}


def test_parse_expression_negative_number():
    name, args, kwargs = parse_expression("some_rule(-1)")
    assert args == [-1]


def test_parse_expression_list_argument():
    name, args, kwargs = parse_expression('some_rule(["Archery", "Craft"])')
    assert args == [["Archery", "Craft"]]


@pytest.mark.parametrize(
    "expr",
    [
        "not a call at all",
        "1 + 1",
        "some_module.some_rule(2)",  # attribute access on the callee
        "some_rule(other_call(2))",  # nested call as an argument
        "some_rule(x)",  # bare name as an argument (not a literal)
        "some_rule(**kwargs)",
        "import os",
        "__import__('os').system('echo hi')",
    ],
)
def test_parse_expression_rejects_unsafe_or_malformed_expressions(expr):
    with pytest.raises(ConstraintParseError):
        parse_expression(expr)


# --- resolve_target ---


def test_resolve_target_family_only_returns_every_member():
    members = [camper("Chris"), camper("Sam"), camper("Tom")]
    other_family = camper("Other", family="001/Other")

    resolved = resolve_target("022/Glen", None, members + [other_family])

    assert set(resolved) == set(members)


def test_resolve_target_family_and_camper_name_returns_just_that_camper():
    chris = camper("Chris")
    sam = camper("Sam")

    resolved = resolve_target("022/Glen", "Sam", [chris, sam])

    assert resolved == (sam,)


def test_resolve_target_unknown_family_raises():
    with pytest.raises(ConstraintParseError, match="022/Glen"):
        resolve_target("022/Glen", None, [camper("Chris", family="001/Other")])


def test_resolve_target_unknown_camper_raises():
    with pytest.raises(ConstraintParseError, match="Nonexistent"):
        resolve_target("022/Glen", "Nonexistent", [camper("Chris")])


# --- build_constraint_instances ---


def test_build_constraint_instances_happy_path():
    chris = camper("Chris")
    sam = camper("Sam")
    records = [
        {"family_id": "022/Glen", "camper_name": "", "constraint": "no_activities_on_day(2)", "severity": "hard"},
        {
            "family_id": "022/Glen",
            "camper_name": "Sam",
            "constraint": 'no_activity_before(time="11:00")',
            "severity": "soft",
            "note": "sleeps in",
        },
    ]

    instances = build_constraint_instances(records, [chris, sam])

    assert len(instances) == 2
    assert set(instances[0].targets) == {chris, sam}
    assert isinstance(instances[0].rule, NoActivitiesOnDay)
    assert instances[0].severity == "hard"
    assert instances[1].targets == (sam,)
    assert isinstance(instances[1].rule, NoActivityBefore)
    assert instances[1].severity == "soft"
    assert instances[1].note == "sleeps in"


def test_build_constraint_instances_collects_every_bad_row():
    records = [
        {"family_id": "999/Nobody", "camper_name": "", "constraint": "no_activities_on_day(2)", "severity": "hard"},
        {"family_id": "022/Glen", "camper_name": "", "constraint": "not_a_call", "severity": "hard"},
        {"family_id": "022/Glen", "camper_name": "", "constraint": "unknown_rule(1)", "severity": "hard"},
        {"family_id": "022/Glen", "camper_name": "", "constraint": "not_on_activity(activity='Archery')", "severity": "bogus"},
    ]

    with pytest.raises(ConstraintParseError) as excinfo:
        build_constraint_instances(records, [camper("Chris")])

    message = str(excinfo.value)
    assert "Row 1" in message and "999/Nobody" in message
    assert "Row 2" in message
    assert "Row 3" in message and "unknown_rule" in message
    assert "Row 4" in message and "bogus" in message


def test_build_constraint_instances_reports_invalid_arguments_for_a_known_rule():
    records = [
        {"family_id": "022/Glen", "camper_name": "", "constraint": "no_activities_on_day()", "severity": "hard"},
    ]

    with pytest.raises(ConstraintParseError, match="no_activities_on_day"):
        build_constraint_instances(records, [camper("Chris")])
