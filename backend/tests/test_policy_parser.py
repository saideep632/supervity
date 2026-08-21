"""Tests for the deterministic fallback parser (no network/LLM calls)."""

from app.policy_parser import heuristic_parse
from app.models import PolicyCreate, Rule, Action


def test_heuristic_parse_produces_valid_rules():
    text = (
        "Auto-approve expenses under $500 for Sales. "
        "Escalate expenses above $2000. "
        "Reject expenses containing prohibited categories."
    )
    raw = heuristic_parse(text)
    rules = [Rule(**r) for r in raw["rules"]]
    assert len(rules) >= 2
    actions = {r.action for r in rules}
    assert Action.APPROVE in actions or Action.ESCALATE in actions


def test_heuristic_parse_never_produces_empty_rule_list():
    raw = heuristic_parse("This text has no recognizable policy pattern in it at all.")
    assert len(raw["rules"]) >= 1


def test_heuristic_parse_disambiguates_department_vs_category():
    """'Travel' must map to category (matches Claim.category in sample data),
    not department, so it doesn't collide with 'Sales' on the same field."""
    text = "Sales expenses under $1000 are approved. Travel expenses above $500 must be escalated."
    raw = heuristic_parse(text)
    rules = [Rule(**r) for r in raw["rules"]]

    sales_rule = next(r for r in rules if r.action == Action.APPROVE)
    travel_rule = next(r for r in rules if r.action == Action.ESCALATE)

    sales_fields = {c.field for c in sales_rule.conditions}
    travel_fields = {c.field for c in travel_rule.conditions}

    assert "department" in sales_fields
    assert "category" in travel_fields
    assert "department" not in travel_fields  # regression guard


def test_heuristic_parse_output_round_trips_through_policy_create():
    text = "Auto-approve expenses under $500 for Sales. Escalate expenses above $2000."
    raw = heuristic_parse(text)
    rules = [Rule(**r) for r in raw["rules"]]
    draft = PolicyCreate(
        name="Test",
        natural_language=text,
        rules=rules,
        default_action=Action(raw["default_action"]),
        required_fields=raw["required_fields"],
    )
    assert draft.name == "Test"
