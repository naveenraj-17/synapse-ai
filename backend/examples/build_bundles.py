#!/usr/bin/env python3
"""Build Synapse example bundle files from raw example data."""
import json
import os
from datetime import datetime, timezone

EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTED_AT = "2026-04-04T00:00:00Z"

# Load raw data
agents = json.load(open(os.path.join(EXAMPLES_DIR, "user_agents.example.json")))
orchestrations = json.load(open(os.path.join(EXAMPLES_DIR, "orchestrations.example.json")))
mcp_servers = json.load(open(os.path.join(EXAMPLES_DIR, "mcp_servers.example.json")))

# Helper to pick agents by id
def pick_agents(ids):
    return [a for a in agents if a["id"] in ids]

def pick_orchs(ids):
    return [o for o in orchestrations if o["id"] in ids]

BUNDLE_BASE = {
    "synapse_export": True,
    "version": "1.0",
    "exported_at": EXPORTED_AT,
    "has_python_tools": False,
    "custom_tools": []
}

# ── Starter Pack ─────────────────────────────────────────────────────────────
starter = {
    **BUNDLE_BASE,
    "agents": pick_agents(["agent_personal_assistant", "agent_web_researcher"]),
    "orchestrations": pick_orchs(["orch_content_pipeline"]),
    "mcp_servers": [],
}
with open(os.path.join(EXAMPLES_DIR, "starter_pack.bundle.json"), "w") as f:
    json.dump(starter, f, indent=2)
print("✓ starter_pack.bundle.json")

# ── Developer Pack ───────────────────────────────────────────────────────────
developer = {
    **BUNDLE_BASE,
    "agents": pick_agents(["agent_code_reviewer", "agent_software_engineer", "agent_qa_engineer", "agent_deployment_monitor"]),
    "orchestrations": pick_orchs(["orch_dev_pipeline", "orch_pr_review_pipeline"]),
    "mcp_servers": [],
}
with open(os.path.join(EXAMPLES_DIR, "developer_pack.bundle.json"), "w") as f:
    json.dump(developer, f, indent=2)
print("✓ developer_pack.bundle.json")

# ── Productivity Pack ─────────────────────────────────────────────────────────
productivity = {
    **BUNDLE_BASE,
    "agents": pick_agents(["agent_data_analyst", "agent_content_writer", "agent_jira_analyst", "agent_slack_notifier"]),
    "orchestrations": pick_orchs(["orch_market_intelligence"]),
    "mcp_servers": [],
}
with open(os.path.join(EXAMPLES_DIR, "productivity_pack.bundle.json"), "w") as f:
    json.dump(productivity, f, indent=2)
print("✓ productivity_pack.bundle.json")

# ── MCP Pack ─────────────────────────────────────────────────────────────────
mcp = {
    **BUNDLE_BASE,
    "agents": [],
    "orchestrations": [],
    "mcp_servers": mcp_servers,
}
with open(os.path.join(EXAMPLES_DIR, "mcp_pack.bundle.json"), "w") as f:
    json.dump(mcp, f, indent=2)
print("✓ mcp_pack.bundle.json")

print("\nAll bundles built successfully!")
