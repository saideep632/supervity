"""
Tests for the deterministic rules engine. These never touch the LLM or the
FastAPI app — they exercise `app.rules_engine.evaluate_claim` directly
against hand-built `Policy` and `Claim` objects, proving the engine is
testable (and correct) completely independently of the UI and the parser.
"""

import pytest

from app.models import (
    Action,
    Claim,
    Condition,
    Operator,
    Policy,
    Rule,
)
from app.rules_engine import evaluate_claim


def make_policy(rules, default_action=Action.ESCALATE, required_fields=None):
    return Policy(
        name="Test Policy",
        natural_language="test",
        rules=rules,
        default_action=default_action,
        required_fields=required_fields if required_fields is not None else ["amount", "department"],
    )


# ---------------------------------------------------------------------------
# 1. Normal approval
# ---------------------------------------------------------------------------

def test_normal_approval():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.APPROVE,
            conditions=[
                Condition(field="department", operator=Operator.EQUALS, value="Sales"),
                Condition(field="amount", operator=Operator.LESS_THAN, value=500),
            ],
        ),
    ])
    claim = Claim(claim_id="C1", employee="A", department="Sales", amount=250)
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.APPROVE
    assert result.winning_rule_id == "R001"
    assert "R001" in result.matched_rules


# ---------------------------------------------------------------------------
# 2. Normal rejection
# ---------------------------------------------------------------------------

def test_normal_rejection():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.REJECT,
            conditions=[Condition(field="category", operator=Operator.EQUALS, value="Prohibited")],
        ),
    ])
    claim = Claim(claim_id="C2", employee="B", department="Marketing", amount=120, category="Prohibited")
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.REJECT
    assert result.winning_rule_id == "R001"


# ---------------------------------------------------------------------------
# 3. Escalation
# ---------------------------------------------------------------------------

def test_escalation_above_threshold():
    policy = make_policy([
        Rule(
            id="R002", priority=1, action=Action.ESCALATE,
            conditions=[Condition(field="amount", operator=Operator.GREATER_THAN, value=2000)],
        ),
    ])
    claim = Claim(claim_id="EXP-104", employee="D", department="Finance", amount=2350)
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.ESCALATE
    assert "2,350" in result.reason or "2350" in result.reason


# ---------------------------------------------------------------------------
# 4. Boundary values
# ---------------------------------------------------------------------------

def test_boundary_exactly_500_does_not_match_strict_less_than():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.APPROVE,
            conditions=[Condition(field="amount", operator=Operator.LESS_THAN, value=500)],
        ),
    ], default_action=Action.ESCALATE)
    claim = Claim(claim_id="EXP-105", employee="E", department="Sales", amount=500)
    result = evaluate_claim(policy, claim)
    # 500 is NOT < 500, so this must NOT approve — it must fall through to default.
    assert result.decision == Action.ESCALATE
    assert result.matched_rules == []
    trace = result.evaluation_trace[0]
    assert trace.matched is False
    assert "500" in trace.reason


def test_boundary_exactly_2000_matches_greater_or_equal():
    policy = make_policy([
        Rule(
            id="R002", priority=1, action=Action.ESCALATE,
            conditions=[Condition(field="amount", operator=Operator.GREATER_THAN_OR_EQUAL, value=2000)],
        ),
    ])
    claim = Claim(claim_id="EXP-106", employee="F", department="Operations", amount=2000)
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.ESCALATE
    assert result.winning_rule_id == "R002"


# ---------------------------------------------------------------------------
# 5. Conflicting rules -> priority resolution
# ---------------------------------------------------------------------------

def test_conflicting_rules_lower_priority_number_wins():
    policy = make_policy([
        Rule(
            id="RA", priority=1, action=Action.APPROVE,
            conditions=[
                Condition(field="department", operator=Operator.EQUALS, value="Sales"),
                Condition(field="amount", operator=Operator.LESS_THAN, value=1000),
            ],
        ),
        Rule(
            id="RB", priority=2, action=Action.ESCALATE,
            conditions=[
                Condition(field="category", operator=Operator.EQUALS, value="Travel"),
                Condition(field="amount", operator=Operator.GREATER_THAN, value=500),
            ],
        ),
    ])
    claim = Claim(claim_id="EXP-107", employee="G", department="Sales", amount=700, category="Travel")
    result = evaluate_claim(policy, claim)
    # Both RA and RB match; RA has the lower priority number so it wins.
    assert set(result.matched_rules) == {"RA", "RB"}
    assert result.winning_rule_id == "RA"
    assert result.decision == Action.APPROVE
    assert "RB" in result.reason  # conflict must be surfaced, not hidden


def test_same_priority_tie_break_prefers_more_conservative_action():
    policy = make_policy([
        Rule(
            id="RC", priority=1, action=Action.ESCALATE,
            conditions=[Condition(field="amount", operator=Operator.GREATER_THAN, value=100)],
        ),
        Rule(
            id="RD", priority=1, action=Action.REJECT,
            conditions=[Condition(field="category", operator=Operator.EQUALS, value="Prohibited")],
        ),
    ])
    claim = Claim(claim_id="C3", employee="H", department="Sales", amount=200, category="Prohibited")
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.REJECT  # REJECT more conservative than ESCALATE at same priority


# ---------------------------------------------------------------------------
# 6. Missing fields
# ---------------------------------------------------------------------------

def test_missing_required_field_escalates_without_hallucination():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.APPROVE,
            conditions=[Condition(field="department", operator=Operator.EQUALS, value="Sales")],
        ),
    ], required_fields=["amount", "department"])
    claim = Claim(claim_id="EXP-108", employee="I", department=None, amount=340)
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.ESCALATE
    assert result.requires_review is True
    assert "department" in result.reason


def test_missing_field_referenced_by_condition_fails_safe():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.APPROVE,
            conditions=[Condition(field="amount", operator=Operator.LESS_THAN, value=500)],
        ),
    ], required_fields=["department"])  # amount not "required" but still referenced
    claim = Claim(claim_id="EXP-111", employee="J", department="Engineering", amount=None)
    result = evaluate_claim(policy, claim)
    # amount is missing so the condition can't be evaluated -> rule doesn't match -> default action
    assert result.matched_rules == []
    assert result.evaluation_trace[0].matched is False


# ---------------------------------------------------------------------------
# 7. Malformed policy is rejected by schema validation
# ---------------------------------------------------------------------------

def test_malformed_policy_unknown_field_rejected():
    with pytest.raises(Exception):
        Condition(field="not_a_real_field", operator=Operator.EQUALS, value="x")


def test_malformed_policy_numeric_operator_with_string_value_rejected():
    with pytest.raises(Exception):
        Condition(field="amount", operator=Operator.LESS_THAN, value="not-a-number")


def test_policy_requires_at_least_one_rule():
    with pytest.raises(Exception):
        Policy(name="Empty", natural_language="x", rules=[])


def test_duplicate_rule_ids_rejected():
    with pytest.raises(Exception):
        make_policy([
            Rule(id="DUP", priority=1, action=Action.APPROVE,
                 conditions=[Condition(field="amount", operator=Operator.LESS_THAN, value=10)]),
            Rule(id="DUP", priority=2, action=Action.REJECT,
                 conditions=[Condition(field="amount", operator=Operator.GREATER_THAN, value=10)]),
        ])


# ---------------------------------------------------------------------------
# 8. Multiple matching rules (non-conflicting actions, still traceable)
# ---------------------------------------------------------------------------

def test_multiple_matching_rules_same_action_traced_individually():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.ESCALATE,
            conditions=[Condition(field="amount", operator=Operator.GREATER_THAN, value=1000)],
        ),
        Rule(
            id="R002", priority=2, action=Action.ESCALATE,
            conditions=[Condition(field="category", operator=Operator.EQUALS, value="Conference")],
        ),
    ])
    claim = Claim(claim_id="EXP-102", employee="K", department="Engineering", amount=4500, category="Conference")
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.ESCALATE
    assert set(result.matched_rules) == {"R001", "R002"}
    assert result.winning_rule_id == "R001"  # lower priority number wins
    assert len(result.evaluation_trace) == 2


# ---------------------------------------------------------------------------
# Default action fallback when nothing matches
# ---------------------------------------------------------------------------

def test_no_rule_matches_falls_back_to_default_action():
    policy = make_policy([
        Rule(
            id="R001", priority=1, action=Action.REJECT,
            conditions=[Condition(field="category", operator=Operator.EQUALS, value="Prohibited")],
        ),
    ], default_action=Action.ESCALATE)
    claim = Claim(claim_id="EXP-109", employee="L", department="Legal", amount=180, category="Miscellaneous")
    result = evaluate_claim(policy, claim)
    assert result.decision == Action.ESCALATE
    assert result.matched_rules == []
    assert "default" in result.reason.lower()
