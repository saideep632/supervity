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
import tempfile
import threading
from pathlib import Path

from app.models import Policy

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
POLICIES_FILE = DATA_DIR / "policies.json"
_active_policies_file: Path | None = None
_memory_policies: list[Policy] = []

_lock = threading.Lock()


def _ensure_store() -> bool:
    global _active_policies_file
    if _active_policies_file is not None:
        return True
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not POLICIES_FILE.exists():
            POLICIES_FILE.write_text("[]")
        _active_policies_file = POLICIES_FILE
        return True
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "supervity-policies.json"
        try:
            if not fallback.exists():
                fallback.write_text("[]")
            _active_policies_file = fallback
            return True
        except OSError:
            return False


def load_policies() -> list[Policy]:
    if os.environ.get("VERCEL"):
        return list(_memory_policies)
    if not _ensure_store():
        return []
    with _lock:
        try:
            raw = json.loads(_active_policies_file.read_text())
        except (OSError, json.JSONDecodeError):
            return []
    return [Policy(**p) for p in raw]


def save_policies(policies: list[Policy]) -> None:
    if os.environ.get("VERCEL"):
        _memory_policies.clear()
        _memory_policies.extend(policies)
        return
    if not _ensure_store():
        raise OSError("No writable policy storage is available")
    with _lock:
        _active_policies_file.write_text(
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
