from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.models import (
    Claim,
    EvaluationResult,
    Policy,
    PolicyCreate,
    PolicyParseRequest,
    PolicyParseResponse,
    PolicyUpdate,
)
from app.policy_parser import parse_policy_text
from app.rules_engine import evaluate_batch, evaluate_claim
from app.sample_data import SAMPLE_CLAIMS
from app import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy_agent")

app = FastAPI(
    title="Supervity Policy-Driven Approval Agent",
    description=(
        "Converts plain-English expense policies into structured, validated "
        "rules and evaluates claims against them with a fully deterministic "
        "rules engine. The LLM never makes the final decision."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://saideep632.github.io",
        "https://supervity.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@app.post("/api/policies/parse", response_model=PolicyParseResponse)
def parse_policy(req: PolicyParseRequest):
    """
    Stage 1 of the pipeline: natural language -> structured DRAFT.

    This endpoint does NOT persist anything and is never used for decisions
    directly. The frontend shows the draft to the user, who can edit it,
    before calling POST /api/policies to validate + save it.
    """
    try:
        draft, parser_used, warnings = parse_policy_text(req.text, name=req.name)
    except ValidationError as exc:
        logger.warning("Policy parse produced invalid schema: %s", exc)
        raise HTTPException(
            status_code=422,
            detail=f"Parsed policy failed schema validation: {exc.errors()}",
        )
    except Exception as exc:
        logger.exception("Policy parsing failed entirely")
        raise HTTPException(status_code=500, detail=f"Policy parsing failed: {exc}")

    return PolicyParseResponse(policy_draft=draft, parser_used=parser_used, warnings=warnings)


@app.post("/api/policies", response_model=Policy, status_code=201)
def create_policy(draft: PolicyCreate):
    """
    Stage 2: DRAFT -> VALIDATED, PERSISTED policy.

    Re-validates through the `Policy` model (not just `PolicyCreate`) so a
    hand-edited or LLM-produced draft cannot skip full-object validation
    (unique rule ids, non-empty conditions, etc) on its way into storage.
    """
    try:
        policy = Policy(**draft.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    storage.upsert_policy(policy)
    logger.info("Created policy %s (%s) with %d rules", policy.id, policy.name, len(policy.rules))
    return policy


@app.get("/api/policies", response_model=list[Policy])
def list_policies():
    return storage.load_policies()


@app.get("/api/policies/{policy_id}", response_model=Policy)
def get_policy(policy_id: str):
    policy = storage.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@app.put("/api/policies/{policy_id}", response_model=Policy)
def update_policy(policy_id: str, update: PolicyUpdate):
    existing = storage.get_policy(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found")

    data = existing.model_dump()
    patch = update.model_dump(exclude_unset=True)
    data.update(patch)
    data["updated_at"] = datetime.utcnow()

    try:
        updated = Policy(**data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    storage.upsert_policy(updated)
    return updated


@app.delete("/api/policies/{policy_id}", status_code=204)
def delete_policy(policy_id: str):
    if not storage.delete_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    return None


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

@app.get("/api/claims", response_model=list[Claim])
def list_claims():
    return SAMPLE_CLAIMS


@app.get("/api/claims/{claim_id}", response_model=Claim)
def get_claim(claim_id: str):
    for c in SAMPLE_CLAIMS:
        if c.claim_id == claim_id:
            return c
    raise HTTPException(status_code=404, detail="Claim not found")


@app.post("/api/claims/evaluate", response_model=list[EvaluationResult])
def evaluate_claims(policy_id: str | None = None):
    """
    Evaluate every sample claim against a policy using the DETERMINISTIC
    rules engine only (no LLM call happens in this request at all).

    If policy_id is omitted, the most recently created ACTIVE policy is
    used, matching the natural "evaluate against whatever's active" demo
    flow.
    """
    policies = storage.load_policies()
    if not policies:
        raise HTTPException(status_code=400, detail="No policies configured. Create a policy first.")

    if policy_id:
        policy = next((p for p in policies if p.id == policy_id), None)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
    else:
        active = [p for p in policies if p.active]
        if not active:
            raise HTTPException(status_code=400, detail="No active policy. Activate one first.")
        policy = sorted(active, key=lambda p: p.updated_at, reverse=True)[0]

    results = evaluate_batch(policy, SAMPLE_CLAIMS)
    logger.info("Evaluated %d claims against policy %s", len(results), policy.id)
    return results


@app.post("/api/claims/{claim_id}/evaluate", response_model=EvaluationResult)
def evaluate_single_claim(claim_id: str, policy_id: str):
    claim = next((c for c in SAMPLE_CLAIMS if c.claim_id == claim_id), None)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    policy = storage.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return evaluate_claim(policy, claim)
