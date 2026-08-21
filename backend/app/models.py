"""
Core data models for the Policy-Driven Approval Agent.

These schemas are the contract between every layer of the system:

    Natural language --> Policy Parser --> PolicyDraft (untrusted)
    PolicyDraft --> Validator --> Policy (trusted, persisted)
    Policy + Claim --> Rules Engine --> EvaluationResult

Nothing downstream of `Policy` ever accepts raw LLM output again. Once a
policy is validated and stored, the decision engine only ever reads back
its own validated Pydantic objects.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Action(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    IS_MISSING = "is_missing"
    IS_PRESENT = "is_present"


# Fields a condition is allowed to reference. Keeping this an explicit
# allow-list (rather than trusting whatever field name the LLM invents)
# is part of how we stop free-form model output from reaching the engine.
ALLOWED_FIELDS = {
    "amount",
    "department",
    "category",
    "employee",
    "description",
    "date",
}

NUMERIC_OPERATORS = {
    Operator.LESS_THAN,
    Operator.LESS_THAN_OR_EQUAL,
    Operator.GREATER_THAN,
    Operator.GREATER_THAN_OR_EQUAL,
}

LIST_OPERATORS = {Operator.IN, Operator.NOT_IN}

NULLARY_OPERATORS = {Operator.IS_MISSING, Operator.IS_PRESENT}


# ---------------------------------------------------------------------------
# Policy / rule schema
# ---------------------------------------------------------------------------

class Condition(BaseModel):
    field: str
    operator: Operator
    value: Any = None

    @field_validator("field")
    @classmethod
    def field_must_be_allowed(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_FIELDS:
            raise ValueError(
                f"Unknown field '{v}'. Allowed fields: {sorted(ALLOWED_FIELDS)}"
            )
        return v

    @model_validator(mode="after")
    def validate_value_for_operator(self) -> "Condition":
        if self.operator in NULLARY_OPERATORS:
            # is_missing / is_present take no value
            return self
        if self.operator in NUMERIC_OPERATORS:
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ValueError(
                    f"Operator '{self.operator}' on field '{self.field}' requires a "
                    f"numeric value, got {self.value!r}"
                )
        if self.operator in LIST_OPERATORS:
            if not isinstance(self.value, list) or len(self.value) == 0:
                raise ValueError(
                    f"Operator '{self.operator}' on field '{self.field}' requires a "
                    f"non-empty list value, got {self.value!r}"
                )
        if self.operator in (Operator.EQUALS, Operator.NOT_EQUALS,
                              Operator.CONTAINS, Operator.NOT_CONTAINS):
            if self.value is None or (isinstance(self.value, str) and not self.value.strip()):
                raise ValueError(
                    f"Operator '{self.operator}' on field '{self.field}' requires a "
                    f"non-empty value"
                )
        return self


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: f"R{uuid4().hex[:6].upper()}")
    name: str = ""
    priority: int = Field(ge=1, description="Lower number = higher priority")
    conditions: list[Condition] = Field(min_length=1)
    match: Literal["all", "any"] = "all"
    action: Action
    source_text: Optional[str] = None  # the plain-English clause this came from

    @field_validator("conditions")
    @classmethod
    def conditions_not_empty(cls, v: list[Condition]) -> list[Condition]:
        if not v:
            raise ValueError("A rule must have at least one condition")
        return v


class Policy(BaseModel):
    id: str = Field(default_factory=lambda: f"POL-{uuid4().hex[:8].upper()}")
    name: str
    natural_language: str
    rules: list[Rule] = Field(min_length=1)
    active: bool = True
    default_action: Action = Action.ESCALATE
    required_fields: list[str] = Field(default_factory=lambda: ["amount", "department"])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("rules")
    @classmethod
    def unique_rule_ids(cls, v: list[Rule]) -> list[Rule]:
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule IDs must be unique within a policy")
        return v


class PolicyCreate(BaseModel):
    name: str
    natural_language: str
    rules: list[Rule]
    default_action: Action = Action.ESCALATE
    required_fields: list[str] = Field(default_factory=lambda: ["amount", "department"])


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    natural_language: Optional[str] = None
    rules: Optional[list[Rule]] = None
    active: Optional[bool] = None
    default_action: Optional[Action] = None
    required_fields: Optional[list[str]] = None


class PolicyParseRequest(BaseModel):
    text: str = Field(min_length=3)
    name: str = "Untitled Policy"


class PolicyParseResponse(BaseModel):
    policy_draft: PolicyCreate
    parser_used: Literal["llm", "fallback_heuristic"]
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

class Claim(BaseModel):
    claim_id: str
    employee: str
    department: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None


# ---------------------------------------------------------------------------
# Evaluation results
# ---------------------------------------------------------------------------

class RuleTrace(BaseModel):
    rule_id: str
    rule_name: str
    matched: bool
    reason: str
    action: Action
    priority: int
    condition_results: list[dict] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    claim_id: str
    decision: Action
    matched_rules: list[str]
    winning_rule_id: Optional[str] = None
    reason: str
    explanation: str
    evaluation_trace: list[RuleTrace]
    requires_review: bool = False
    policy_id: str
    policy_name: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
