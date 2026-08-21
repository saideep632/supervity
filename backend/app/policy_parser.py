"""
Natural-language -> structured policy parser.

CRITICAL BOUNDARY: this module produces a `PolicyCreate` DRAFT. That draft
is *untrusted* output. It is always re-validated by Pydantic (models.py)
and never handed directly to the rules engine — main.py always round-trips
it through `Policy(**draft.model_dump())` before persistence, and only
persisted, validated `Policy` objects are ever evaluated.

Two parsing strategies:
  1. `llm_parse`     - calls an OpenAI-compatible chat completions API and
                        asks the model to emit ONLY a JSON object matching
                        our schema. If the API key is missing or the call
                        fails, we fall back automatically.
  2. `heuristic_parse` - a small deterministic regex/keyword parser that
                        handles the common phrasings used in the assessment
                        brief ("under $X", "above $X", "prohibited
                        category", department names, etc). This guarantees
                        the app is fully demoable with zero API key and
                        gives us a deterministic fallback when the LLM is
                        unavailable or returns garbage, per the "provide
                        deterministic fallback behavior" requirement.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from app.models import Action, Condition, Operator, PolicyCreate, Rule

SYSTEM_PROMPT = """You convert plain-English business expense-approval policies into a strict JSON object.

Output ONLY valid JSON. No markdown fences, no commentary, no explanation.

Schema:
{
  "rules": [
    {
      "name": "short human label",
      "priority": <int, 1 = highest priority, evaluated first>,
      "match": "all" | "any",
      "conditions": [
        {"field": "<amount|department|category|employee|description|date>",
         "operator": "<equals|not_equals|<|<=|>|>=|contains|not_contains|in|not_in|is_missing|is_present>",
         "value": <number, string, or list depending on operator; omit for is_missing/is_present>}
      ],
      "action": "APPROVE" | "REJECT" | "ESCALATE",
      "source_text": "<the exact clause of the input this rule came from>"
    }
  ],
  "default_action": "APPROVE" | "REJECT" | "ESCALATE",
  "required_fields": ["amount", "department"]
}

Rules for interpretation:
- "under $X" / "below $X" means strictly less than X (operator "<"), NOT less-than-or-equal.
- "over $X" / "above $X" means strictly greater than X (operator ">").
- "at least $X" means ">=". "at most $X" means "<=".
- Give earlier/more specific clauses in the input a LOWER priority number (evaluated first / higher precedence)
  than general catch-all clauses.
- REJECT and ESCALATE rules should generally get a LOWER priority number (higher precedence) than APPROVE rules,
  even if the APPROVE clause is written first in the source text — a blocking/review rule (e.g. "prohibited
  category") must win over a permissive rule (e.g. "under $500 auto-approve") unless the text explicitly says
  otherwise.
- If the input doesn't state a default action for unmatched claims, set "default_action" to "ESCALATE" (safe default).
- Never invent fields, categories, or thresholds that are not implied by the text.
- If a clause is ambiguous, still produce your best-effort structured rule but keep it conservative
  (route to ESCALATE rather than APPROVE when in doubt).
- Category/department names should be Title Case matching how they appear in the text (e.g. "Sales", "Travel").
- "Travel", "Conference", "Equipment", "Software" and similar expense TYPES are the "category" field, not
  "department". Organizational units like "Sales", "Engineering", "Marketing", "Finance" are "department".
  Do not conflate the two even when a sentence only says e.g. "Travel expenses" with no explicit field label.
"""


def _get_client():
    """Return an OpenAI-compatible client if configured, else None."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL")  # optional, for OpenAI-compatible providers
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def llm_parse(text: str) -> Optional[dict]:
    """Attempt to parse policy text via an LLM. Returns raw dict or None on any failure."""
    client = _get_client()
    if client is None:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        content = response.choices[0].message.content
        content = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        data = json.loads(content)
        return data
    except Exception:
        # Deliberately swallow: caller falls back to the deterministic parser.
        # A production system would log this (see app.logging_utils).
        return None


# ---------------------------------------------------------------------------
# Deterministic heuristic fallback parser
# ---------------------------------------------------------------------------

_AMOUNT_RE = r"\$?\s?([\d,]+(?:\.\d+)?)"
# NOTE: "Travel" is deliberately a CATEGORY, not a department, matching the
# claim schema (Claim.category vs Claim.department) — see _CATEGORIES below.
# Keeping these two lists disjoint is what lets "Sales expenses under $1000"
# and "Travel expenses above $500" resolve as a genuine field conflict
# (department vs category) rather than colliding on the same field.
_DEPARTMENTS = ["sales", "engineering", "marketing", "finance", "hr", "operations", "legal"]
_CATEGORIES = ["travel", "conference", "equipment", "software", "client dinner", "client gift", "office supplies"]
_PROHIBITED_KEYWORDS = ["prohibited", "banned", "forbidden", "disallowed"]


def heuristic_parse(text: str) -> dict:
    """Small deterministic keyword/regex parser covering the phrasings in the brief."""
    clauses = re.split(r"[.\n]|(?<=[a-z])\s+(?=[A-Z][a-z]+ expenses)", text)
    clauses = [c.strip() for c in clauses if c.strip()]

    parsed_clauses: list[dict] = []

    for clause in clauses:
        low = clause.lower()

        dept = next((d for d in _DEPARTMENTS if d in low), None)
        cat = next((c for c in _CATEGORIES if c in low), None)

        amount_match = re.search(_AMOUNT_RE, clause)
        amount_val = float(amount_match.group(1).replace(",", "")) if amount_match else None

        conditions = []
        action = None

        if any(k in low for k in _PROHIBITED_KEYWORDS):
            conditions.append({"field": "category", "operator": "equals", "value": "Prohibited"})
            action = "REJECT"

        elif "escalat" in low and amount_val is not None:
            op = ">=" if "at least" in low else ">"
            conditions.append({"field": "amount", "operator": op, "value": amount_val})
            action = "ESCALATE"

        elif ("approv" in low or "auto-approve" in low or "automatically approved" in low) and amount_val is not None:
            if "under" in low or "below" in low or "less than" in low:
                op = "<"
            elif "at most" in low or "up to" in low:
                op = "<="
            else:
                op = "<"
            conditions.append({"field": "amount", "operator": op, "value": amount_val})
            action = "APPROVE"

        elif "reject" in low and amount_val is not None:
            op = ">" if ("over" in low or "above" in low) else ">="
            conditions.append({"field": "amount", "operator": op, "value": amount_val})
            action = "REJECT"

        if action is None:
            continue  # clause didn't match a recognizable pattern; skip rather than guess

        if dept:
            conditions.append({"field": "department", "operator": "equals", "value": dept.title()})
        if cat:
            conditions.append({"field": "category", "operator": "equals", "value": cat.title()})

        parsed_clauses.append({
            "name": clause[:60],
            "conditions": conditions,
            "action": action,
            "source_text": clause,
        })

    # Priority assignment: REJECT and ESCALATE clauses are given precedence
    # over APPROVE clauses regardless of the order they were written in the
    # source text. This mirrors real-world policy intent — e.g. a
    # "prohibited category" rejection must win over a "under $500 auto
    # approve" rule even though the approval clause might be written first.
    # Order is stable within each conservatism tier (original clause order
    # preserved).
    conservatism_rank = {"REJECT": 0, "ESCALATE": 1, "APPROVE": 2}
    parsed_clauses.sort(key=lambda c: conservatism_rank.get(c["action"], 1))

    rules: list[dict] = []
    for i, c in enumerate(parsed_clauses, start=1):
        rules.append({
            "name": c["name"],
            "priority": i,
            "match": "all",
            "conditions": c["conditions"],
            "action": c["action"],
            "source_text": c["source_text"],
        })

    if not rules:
        # Nothing recognizable — produce a single safe catch-all so the
        # system never silently produces an empty policy.
        rules.append({
            "name": "Unrecognized policy text — manual review required",
            "priority": 1,
            "match": "all",
            "conditions": [{"field": "amount", "operator": ">=", "value": 0}],
            "action": "ESCALATE",
            "source_text": text,
        })

    return {
        "rules": rules,
        "default_action": "ESCALATE",
        "required_fields": ["amount", "department"],
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_policy_text(text: str, name: str = "Untitled Policy") -> tuple[PolicyCreate, str, list[str]]:
    """
    Returns (PolicyCreate draft, parser_used, warnings).

    Tries the LLM first; falls back to the deterministic heuristic parser on
    any failure, missing API key, or malformed LLM output. Either path is
    then rebuilt through Pydantic models, so a malformed/hallucinated field
    name or operator raises a validation error the caller can surface to
    the user rather than silently reaching the decision engine.
    """
    warnings: list[str] = []
    raw = llm_parse(text)
    parser_used = "llm"

    if raw is None:
        raw = heuristic_parse(text)
        parser_used = "fallback_heuristic"
        warnings.append(
            "LLM parser unavailable or failed; used deterministic heuristic "
            "fallback parser instead. Review the generated rules carefully."
        )

    try:
        rules = [Rule(**r) for r in raw["rules"]]
    except Exception as exc:
        # LLM produced something schema-invalid: fall back rather than
        # letting malformed structure anywhere near persistence/eval.
        if parser_used == "llm":
            warnings.append(f"LLM output failed schema validation ({exc}); using heuristic fallback.")
            raw = heuristic_parse(text)
            parser_used = "fallback_heuristic"
            rules = [Rule(**r) for r in raw["rules"]]
        else:
            raise

    draft = PolicyCreate(
        name=name,
        natural_language=text,
        rules=rules,
        default_action=Action(raw.get("default_action", "ESCALATE")),
        required_fields=raw.get("required_fields", ["amount", "department"]),
    )
    return draft, parser_used, warnings
