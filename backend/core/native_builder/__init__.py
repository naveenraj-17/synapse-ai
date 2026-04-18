"""
Native Builder — Synapse's AI Builder implemented as a real orchestration.

This package holds the seed JSON definitions (orchestration + sub-agents) and
the idempotent seeding function used at startup. See seed.py.
"""
from .seed import seed_native_builder, NATIVE_BUILDER_ORCH_ID, NATIVE_BUILDER_AGENT_ID

__all__ = [
    "seed_native_builder",
    "NATIVE_BUILDER_ORCH_ID",
    "NATIVE_BUILDER_AGENT_ID",
    "STEP_TYPE_CHEATSHEET",
]


# Shared step-type reference used by the plan drafter prompt AND the saver
# agents' system prompts so the drafter's plan and the saver's materialised
# JSON agree on the step palette.
#
# Fields listed per type are the ones that MUST be populated for that type
# (beyond the common id/name/type/input_keys/output_key/next_step_id/
# max_turns/timeout_seconds/max_iterations). Unlisted fields may be left at
# their zero-defaults (`route_map: {}`, `parallel_branches: []`, etc.) so the
# engine deserialises cleanly.
STEP_TYPE_CHEATSHEET = """\
- **agent**: runs a configured sub-agent with a prompt + its tool set. Required: `agent_id`, `prompt_template`. Use for any step that needs multi-turn reasoning or tool use.
- **llm**: single one-shot LLM call, no tools. Required: `prompt_template` (optional `model`). Use for lightweight summarisation, rewriting, or deterministic prose generation.
- **tool**: forces a single tool call with no LLM reasoning. Required: `forced_tool` (+ `agent_id` for tool-resolution). Use when the arguments are already in state and just need forwarding.
- **evaluator**: pure routing node. Required: `route_map` (`{label: target_step_id}`), `route_descriptions`, `evaluator_prompt`. Output_key stores the bare route label. Use to fork on a classifier decision.
- **parallel**: runs multiple branches concurrently. Required: `parallel_branches` (list of step-id lists), `next_step_id` (where they converge). Use when independent work can overlap.
- **merge**: combines parallel-branch outputs. Required: `merge_strategy` (`concat` | `list` | `dict`). Place immediately after a parallel's convergence.
- **loop**: runs a body N times. Required: `loop_step_ids` (ordered body), `loop_count`. Use for fixed repetition; for conditional loops use an evaluator that routes back.
- **human**: pauses for user input. Required: `human_prompt`, `human_fields` (list of `{name, type, label}`). Output_key stores the response dict.
- **transform**: runs a snippet of Python against state. Required: `transform_code` — reads `state`, assigns to `result`. Use for pure-data reshapes; avoid heavy logic.
- **end**: terminates the orchestration. No type-specific fields. Every flow must reach an `end` step.

Wiring rules that apply to every step:
- `id` format: `step_` + 7 lowercase-alphanumeric chars, unique within the orchestration.
- `output_key` of an upstream step must appear in the `input_keys` of any downstream step that reads it.
- `entry_step_id` at the orchestration level must match the first step actually executed.
- Agents are referenced by their real `agent_xxxxxxx` ID — never invent one.
- For tool steps, confirm the tool exists via `get_tools_detail` before naming it in `forced_tool`.
"""
