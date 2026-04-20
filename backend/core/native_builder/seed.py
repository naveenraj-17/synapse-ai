"""Idempotent seeding of the native builder orchestration and its sub-agents.

Reads bundled JSON definitions from this package and merges any missing entries
(by id) into data/user_agents.json and data/orchestrations.json.
"""
from __future__ import annotations

import json
import os
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_DIR = os.path.join(_HERE, "agents")
_ORCH_FILE = os.path.join(_HERE, "orchestration.json")

NATIVE_BUILDER_ORCH_ID = "orch_native_builder"
NATIVE_BUILDER_AGENT_ID = "agent_native_builder"

# Agent IDs that were shipped by earlier versions of the native builder and
# should be purged on startup. Kept here so stale entries get cleaned up from
# data/user_agents.json when users upgrade.
LEGACY_BUILDER_AGENT_IDS: set[str] = {
    "agent_native_builder_planner_create",
    "agent_native_builder_planner_update",
}


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _expand_cheatsheet(text: str) -> str:
    # Imported lazily to avoid a circular import (this module is imported from __init__.py).
    from . import STEP_TYPE_CHEATSHEET
    if not isinstance(text, str):
        return text
    return text.replace("{{STEP_TYPE_CHEATSHEET}}", STEP_TYPE_CHEATSHEET)


def _apply_cheatsheet_to_agent(agent: dict) -> dict:
    sp = agent.get("system_prompt")
    if isinstance(sp, str):
        agent["system_prompt"] = _expand_cheatsheet(sp)
    return agent


def _apply_cheatsheet_to_orch(orch: dict) -> dict:
    for step in orch.get("steps", []) or []:
        pt = step.get("prompt_template")
        if isinstance(pt, str):
            step["prompt_template"] = _expand_cheatsheet(pt)
    return orch


def _load_bundled_agents() -> list[dict]:
    if not os.path.isdir(_AGENTS_DIR):
        return []
    out: list[dict] = []
    for name in sorted(os.listdir(_AGENTS_DIR)):
        if name.endswith(".json"):
            out.append(_apply_cheatsheet_to_agent(_load_json(os.path.join(_AGENTS_DIR, name))))
    return out


def _load_bundled_orchestration() -> dict:
    return _apply_cheatsheet_to_orch(_load_json(_ORCH_FILE))


def seed_native_builder() -> dict:
    """Sync the builder orchestration and sub-agents from the bundled definitions.

    Native-builder entries (ids starting with `agent_native_builder` / equal to
    `orch_native_builder`) are always replaced with the bundled version so tool
    list / prompt fixes propagate on restart. Other entries are left alone.

    Returns: {"agents_added": [...], "agents_updated": [...], "agents_removed": [...], "orchestration": "added"|"updated"|"unchanged"}.
    """
    from core.routes.agents import load_user_agents, save_user_agents
    from core.routes.orchestrations import load_orchestrations, save_orchestrations

    bundled_agents = _load_bundled_agents()
    bundled_orch = _load_bundled_orchestration()
    bundled_agent_map = {a["id"]: a for a in bundled_agents}

    existing_agents = load_user_agents()
    agents_added: list[str] = []
    agents_updated: list[str] = []
    agents_removed: list[str] = []
    seen_bundled_ids: set[str] = set()
    new_agents: list[dict] = []
    for a in existing_agents:
        aid = a.get("id")
        if aid in LEGACY_BUILDER_AGENT_IDS:
            agents_removed.append(aid)
            continue
        if aid in bundled_agent_map:
            bundled = bundled_agent_map[aid]
            if a != bundled:
                agents_updated.append(aid)
            new_agents.append(bundled)
            seen_bundled_ids.add(aid)
        else:
            new_agents.append(a)
    for aid, bundled in bundled_agent_map.items():
        if aid not in seen_bundled_ids:
            new_agents.append(bundled)
            agents_added.append(aid)
    if agents_added or agents_updated or agents_removed:
        save_user_agents(new_agents)

    existing_orchs = load_orchestrations()
    orch_status = "unchanged"
    new_orchs: list[dict] = []
    seen_orch = False
    for o in existing_orchs:
        if o.get("id") == bundled_orch["id"]:
            seen_orch = True
            if o != bundled_orch:
                orch_status = "updated"
            new_orchs.append(bundled_orch)
        else:
            new_orchs.append(o)
    if not seen_orch:
        new_orchs.append(bundled_orch)
        orch_status = "added"
    if orch_status != "unchanged":
        save_orchestrations(new_orchs)

    return {
        "agents_added": agents_added,
        "agents_updated": agents_updated,
        "agents_removed": agents_removed,
        "orchestration": orch_status,
    }
