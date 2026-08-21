"""
Deterministic Policy Rules Engine.

This module NEVER calls an LLM and NEVER sees raw natural language. It only
operates on already-validated `Policy` / `Rule` / `Condition` Pydantic
objects and a `Claim`. Given the same policy and claim, it always produces
the same `EvaluationResult` — that determinism is the entire point of
separating this from the LLM policy parser.

Priority / conflict resolution strategy (documented, not implicit):
    1. Evaluate every rule in the active policy against the claim.
    2. Collect all rules whose conditions match.
    3. If zero rules match -> fall back to `policy.default_action`.
    4. If one or more rules match -> the matched rule with the LOWEST
       `priority` number wins (priority 1 beats priority 5).
    5. If REJECT and ESCALATE both match at the same priority, REJECT wins
       (the more conservative/blocking outcome), because silently letting
       money move is worse than an unnecessary human review. This tie-break
       is applied only when priorities are exactly equal.
    6. Every matched AND unmatched rule is recorded in `evaluation_trace`
       with the concrete values compared, so a decision is always
       auditable rule-by-rule.
"""

from __future__ import annotations

from app.models import (
    Action,
    Claim,
    Condition,
    EvaluationResult,
    Operator,
    Policy,
    Rule,
    RuleTrace,
)

# Action conservatism ranking used only for same-priority tie-breaks.
_ACTION_CONSERVATISM = {Action.REJECT: 0, Action.ESCALATE: 1, Action.APPROVE: 2}

_ACTION_PAST_TENSE = {
    Action.APPROVE: "approved",
    Action.REJECT: "rejected",
    Action.ESCALATE: "escalated",
}


def _get_field_value(claim: Claim, field: str):
    return getattr(claim, field, None)


def _evaluate_condition(claim: Claim, cond: Condition) -> tuple[bool, str, dict]:
    """Evaluate a single condition against a claim. Returns (matched, reason, detail)."""
    actual = _get_field_value(claim, cond.field)
    op = cond.operator
    detail = {
        "field": cond.field,
        "operator": op.value,
        "expected": cond.value,
        "actual": actual,
    }

    # Missing-data handling is explicit, never guessed.
    if op == Operator.IS_MISSING:
        matched = actual is None or (isinstance(actual, str) and not actual.strip())
        reason = f"{cond.field} is {'missing' if matched else 'present'} (value={actual!r})"
        return matched, reason, detail

    if op == Operator.IS_PRESENT:
        matched = actual is not None and not (isinstance(actual, str) and not actual.strip())
        reason = f"{cond.field} is {'present' if matched else 'missing'} (value={actual!r})"
        return matched, reason, detail

    if actual is None or (isinstance(actual, str) and not actual.strip()):
        # Cannot evaluate a comparison against missing data. Explicitly
        # marked unmatched with a clear reason rather than throwing or
        # silently defaulting.
        reason = f"{cond.field} is missing, cannot evaluate '{op.value}' condition"
        return False, reason, detail

    try:
        if op == Operator.EQUALS:
            matched = str(actual).strip().lower() == str(cond.value).strip().lower()
            reason = f"{cond.field} '{actual}' {'==' if matched else '!='} '{cond.value}'"
        elif op == Operator.NOT_EQUALS:
            matched = str(actual).strip().lower() != str(cond.value).strip().lower()
            reason = f"{cond.field} '{actual}' {'!=' if matched else '=='} '{cond.value}'"
        elif op == Operator.LESS_THAN:
            matched = float(actual) < float(cond.value)
            reason = f"{cond.field} {actual} {'<' if matched else '>='} {cond.value}"
        elif op == Operator.LESS_THAN_OR_EQUAL:
            matched = float(actual) <= float(cond.value)
            reason = f"{cond.field} {actual} {'<=' if matched else '>'} {cond.value}"
        elif op == Operator.GREATER_THAN:
            matched = float(actual) > float(cond.value)
            reason = f"{cond.field} {actual} {'>' if matched else '<='} {cond.value}"
        elif op == Operator.GREATER_THAN_OR_EQUAL:
            matched = float(actual) >= float(cond.value)
            reason = f"{cond.field} {actual} {'>=' if matched else '<'} {cond.value}"
        elif op == Operator.CONTAINS:
            matched = str(cond.value).strip().lower() in str(actual).strip().lower()
            reason = f"{cond.field} '{actual}' {'contains' if matched else 'does not contain'} '{cond.value}'"
        elif op == Operator.NOT_CONTAINS:
            matched = str(cond.value).strip().lower() not in str(actual).strip().lower()
            reason = f"{cond.field} '{actual}' {'does not contain' if matched else 'contains'} '{cond.value}'"
        elif op == Operator.IN:
            options = [str(x).strip().lower() for x in cond.value]
            matched = str(actual).strip().lower() in options
            reason = f"{cond.field} '{actual}' {'is in' if matched else 'is not in'} {cond.value}"
        elif op == Operator.NOT_IN:
            options = [str(x).strip().lower() for x in cond.value]
            matched = str(actual).strip().lower() not in options
            reason = f"{cond.field} '{actual}' {'is not in' if matched else 'is in'} {cond.value}"
        else:  # pragma: no cover - guarded by enum, defensive only
            matched = False
            reason = f"Unsupported operator '{op.value}'"
    except (TypeError, ValueError) as exc:
        matched = False
        reason = f"Could not compare {cond.field}={actual!r} using '{op.value}': {exc}"

    return matched, reason, detail


def _evaluate_rule(claim: Claim, rule: Rule) -> RuleTrace:
    condition_results = []
    matches = []
    for cond in rule.conditions:
        matched, reason, detail = _evaluate_condition(claim, cond)
        detail["matched"] = matched
        detail["reason"] = reason
        condition_results.append(detail)
        matches.append(matched)

    rule_matched = all(matches) if rule.match == "all" else any(matches)

    if rule_matched:
        reason_text = "; ".join(d["reason"] for d in condition_results)
    else:
        failing = [d["reason"] for d in condition_results if not d["matched"]]
        reason_text = "; ".join(failing) if failing else "No conditions matched"

    return RuleTrace(
        rule_id=rule.id,
        rule_name=rule.name or rule.id,
        matched=rule_matched,
        reason=reason_text,
        action=rule.action,
        priority=rule.priority,
        condition_results=condition_results,
    )


def evaluate_claim(policy: Policy, claim: Claim) -> EvaluationResult:
    """Evaluate a single claim against a policy. Pure function, fully deterministic."""

    # --- Explicit missing-required-field handling (no hallucination) ---
    missing_required = [
        f for f in policy.required_fields
        if _get_field_value(claim, f) is None
        or (isinstance(_get_field_value(claim, f), str) and not _get_field_value(claim, f).strip())
    ]

    trace: list[RuleTrace] = [_evaluate_rule(claim, rule) for rule in sorted(policy.rules, key=lambda r: r.priority)]

    if missing_required:
        fields_str = ", ".join(missing_required)
        reason = f"Required field(s) missing: {fields_str}. Routed to escalation for manual review."
        return EvaluationResult(
            claim_id=claim.claim_id,
            decision=Action.ESCALATE,
            matched_rules=[],
            winning_rule_id=None,
            reason=reason,
            explanation=(
                f"Claim {claim.claim_id} was escalated because required field(s) "
                f"[{fields_str}] were missing, so no rule could be safely evaluated. "
                f"No policy facts were assumed."
            ),
            evaluation_trace=trace,
            requires_review=True,
            policy_id=policy.id,
            policy_name=policy.name,
        )

    matched_traces = [t for t in trace if t.matched]

    if not matched_traces:
        reason = (
            f"No rule matched this claim. Falling back to the policy's default "
            f"action: {policy.default_action.value}."
        )
        return EvaluationResult(
            claim_id=claim.claim_id,
            decision=policy.default_action,
            matched_rules=[],
            winning_rule_id=None,
            reason=reason,
            explanation=(
                f"Claim {claim.claim_id} received the default action "
                f"({policy.default_action.value}) because it did not match any "
                f"configured rule in policy '{policy.name}'."
            ),
            evaluation_trace=trace,
            requires_review=(policy.default_action == Action.ESCALATE),
            policy_id=policy.id,
            policy_name=policy.name,
        )

    # Winner = lowest priority number; ties broken by conservatism (REJECT > ESCALATE > APPROVE)
    winner = min(
        matched_traces,
        key=lambda t: (t.priority, _ACTION_CONSERVATISM[t.action]),
    )

    conflict_note = ""
    if len(matched_traces) > 1:
        other_actions = {t.action for t in matched_traces} - {winner.action}
        if other_actions:
            conflicting_ids = [t.rule_id for t in matched_traces if t.rule_id != winner.rule_id]
            conflict_note = (
                f" Note: rule(s) {', '.join(conflicting_ids)} also matched with a "
                f"different action; rule {winner.rule_id} took precedence "
                f"(priority {winner.priority})."
            )

    reason = f"{winner.reason} -> {winner.action.value} via rule {winner.rule_id}.{conflict_note}"

    return EvaluationResult(
        claim_id=claim.claim_id,
        decision=winner.action,
        matched_rules=[t.rule_id for t in matched_traces],
        winning_rule_id=winner.rule_id,
        reason=reason,
        explanation=(
            f"Claim {claim.claim_id} was {_ACTION_PAST_TENSE[winner.action]} because "
            f"{winner.reason}, under rule {winner.rule_id} "
            f"('{winner.rule_name}')."
            f"{conflict_note}"
        ),
        evaluation_trace=trace,
        requires_review=(winner.action == Action.ESCALATE),
        policy_id=policy.id,
        policy_name=policy.name,
    )


def evaluate_batch(policy: Policy, claims: list[Claim]) -> list[EvaluationResult]:
    return [evaluate_claim(policy, c) for c in claims]
