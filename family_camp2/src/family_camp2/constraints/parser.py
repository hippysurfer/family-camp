"""Turns raw constraint records (REQUIREMENTS.md §3.5's Target/Constraint/
Severity/Note fields, however they arrived - a CSV row, a JSON object, a
Google Sheets row) into resolved ``ConstraintInstance`` objects.

Never ``eval()``: ``parse_expression`` walks the expression's ``ast`` tree
and accepts only a plain function call with literal (constant/list)
arguments - this is organiser-edited spreadsheet data, not trusted source
code (FR-92). Every unresolvable record - a bad target, an unparseable
expression, an unknown rule name, wrong arguments for it - is collected
and reported together, not just the first (FR-93), the same shape
``io/schedule_export.py``'s ``_resolve_rows`` uses for schedule re-import.
"""

from __future__ import annotations

import ast

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.constraints.registry import get_constraint_class
from family_camp2.domain import Camper

__all__ = ["ConstraintParseError", "parse_expression", "resolve_target", "build_constraint_instances"]


class ConstraintParseError(ValueError):
    """Raised when a constraint record can't be resolved to a valid
    ``ConstraintInstance`` - a bad target, an unsafe/unparseable
    expression, an unknown rule name, or invalid arguments for it."""


def _literal(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(
        node.operand, ast.Constant
    ):
        value = node.operand.value
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.List):
        return [_literal(elt) for elt in node.elts]
    raise ConstraintParseError(f"Unsupported expression element: {ast.dump(node)}")


def parse_expression(expr: str) -> tuple[str, list, dict]:
    """Parses a spreadsheet cell like ``no_activities_on_day(2)`` or
    ``no_activity_before(time="11:00")`` into ``(rule_name, args, kwargs)``.
    Accepts only a single call to a bare name with constant/list
    arguments - never executes anything."""

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ConstraintParseError(f"Could not parse constraint expression {expr!r}: {exc}") from exc

    call = tree.body
    if not isinstance(call, ast.Call):
        raise ConstraintParseError(f"Expected a function call like 'rule_name(...)', got: {expr!r}")
    if not isinstance(call.func, ast.Name):
        raise ConstraintParseError(f"Expected a plain rule name, got: {expr!r}")

    name = call.func.id
    args = [_literal(arg) for arg in call.args]
    kwargs: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg is None:
            raise ConstraintParseError(f"**kwargs unpacking is not supported: {expr!r}")
        kwargs[kw.arg] = _literal(kw.value)

    return name, args, kwargs


def resolve_target(family_id: str, camper_name: str | None, campers: list[Camper]) -> tuple[Camper, ...]:
    """A blank/None camper_name resolves to every member of the family
    (§3.5); otherwise to that one camper. Same (family_id, name) lookup
    convention ``io/schedule_export.py`` already established."""

    if camper_name:
        matches = tuple(c for c in campers if c.family_id == family_id and c.name == camper_name)
        if not matches:
            raise ConstraintParseError(f"Unknown camper {camper_name!r} in family {family_id!r}")
        return matches

    matches = tuple(c for c in campers if c.family_id == family_id)
    if not matches:
        raise ConstraintParseError(f"Unknown family {family_id!r}")
    return matches


def _build_one(record: dict, campers: list[Camper]) -> ConstraintInstance:
    family_id = record["family_id"]
    camper_name = record.get("camper_name") or None
    targets = resolve_target(family_id, camper_name, campers)

    severity = record["severity"]
    if severity not in ("hard", "soft"):
        raise ConstraintParseError(f"Unknown severity {severity!r} (expected 'hard' or 'soft')")

    name, args, kwargs = parse_expression(record["constraint"])
    try:
        rule_cls = get_constraint_class(name)
    except KeyError as exc:
        raise ConstraintParseError(str(exc)) from exc

    try:
        rule = rule_cls(*args, **kwargs)
    except TypeError as exc:
        raise ConstraintParseError(f"Invalid arguments for {name!r}: {exc}") from exc

    return ConstraintInstance(targets=targets, rule=rule, severity=severity, note=record.get("note") or "")


def build_constraint_instances(records: list[dict], campers: list[Camper]) -> list[ConstraintInstance]:
    """Resolves every record, collecting *all* unresolvable ones (FR-93)
    rather than stopping at the first."""

    instances: list[ConstraintInstance] = []
    errors: list[str] = []
    for i, record in enumerate(records, start=1):
        try:
            instances.append(_build_one(record, campers))
        except ConstraintParseError as exc:
            errors.append(f"Row {i}: {exc}")

    if errors:
        raise ConstraintParseError(f"{len(errors)} row(s) could not be resolved:\n" + "\n".join(errors))
    return instances
