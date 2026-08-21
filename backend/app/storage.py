"""
Simple JSON-file persistence for the MVP.

Per the assessment brief this is intentionally NOT a real database —
"SQLite or JSON-based persistence for the MVP" is explicitly allowed, and
JSON keeps the demo/setup friction near zero. Swapping this module for a
SQLite-backed one later would not require touching the engine, parser, or
API layer since they only ever depend on the Pydantic models.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.models import Policy

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
POLICIES_FILE = DATA_DIR / "policies.json"

_lock = threading.Lock()


def _ensure_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not POLICIES_FILE.exists():
        POLICIES_FILE.write_text("[]")


def load_policies() -> list[Policy]:
    _ensure_store()
    with _lock:
        raw = json.loads(POLICIES_FILE.read_text())
    return [Policy(**p) for p in raw]


def save_policies(policies: list[Policy]) -> None:
    _ensure_store()
    with _lock:
        POLICIES_FILE.write_text(
            json.dumps([json.loads(p.model_dump_json()) for p in policies], indent=2, default=str)
        )


def get_policy(policy_id: str) -> Policy | None:
    for p in load_policies():
        if p.id == policy_id:
            return p
    return None


def upsert_policy(policy: Policy) -> Policy:
    policies = load_policies()
    for i, p in enumerate(policies):
        if p.id == policy.id:
            policies[i] = policy
            save_policies(policies)
            return policy
    policies.append(policy)
    save_policies(policies)
    return policy


def delete_policy(policy_id: str) -> bool:
    policies = load_policies()
    new_policies = [p for p in policies if p.id != policy_id]
    if len(new_policies) == len(policies):
        return False
    save_policies(new_policies)
    return True
