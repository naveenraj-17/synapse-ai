"""
Origin-aware context building for orchestration steps.

Provides:
  - TransitionContext   dataclass that describes how a step was invoked
  - build_workflow_graph_markdown()  compact workflow map for system prompt
  - build_execution_trace()       extract structured trace from SSE events
  - store_execution_memory()      persist trace in shared_state
  - get_execution_memory()        retrieve past traces for a step
  - build_transition_context()    determine origin type from run state
  - build_origin_aware_context()  construct the structured prompt + sys-prompt addition
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models_orchestration import StepConfig, OrchestrationRun
    from .engine import OrchestrationEngine


# ---------------------------------------------------------------------------
# TransitionContext
# ---------------------------------------------------------------------------

@dataclass
class TransitionContext:
    """Describes how the current step was invoked."""

    origin_type: str               # "entry" | "linear" | "evaluator" | "loop" | "human_response"
    execution_number: int = 1      # 1 = first time this step runs

    # Who handed control here
    from_step_id: str | None = None
    from_step_name: str | None = None
    from_agent_name: str | None = None

    # Evaluator-specific
    routing_decision: str | None = None    # e.g. "needs_improvement"
    routing_reasoning: str | None = None   # evaluator's explanation

    # Loop-specific
    loop_iteration: int | None = None
    loop_total: int | None = None

    # Human-specific
    human_response_key: str | None = None


def build_transition_context(
    step: "StepConfig",
    run: "OrchestrationRun",
    engine: "OrchestrationEngine",
) -> TransitionContext:
    """
    Derive the TransitionContext for `step` from current run state.
    Called by the engine right before executor.execute().
    """
    from core.models_orchestration import StepType

    # How many times has this step already run?
    exec_count = sum(1 for h in run.step_history if h["step_id"] == step.id)
    execution_number = exec_count + 1  # +1 because we're about to run it

    # Find the most recent completed step (the one that handed us control)
    last_completed = None
    for h in reversed(run.step_history):
        if h.get("status") == "completed":
            last_completed = h
            break

    from_step_id = last_completed["step_id"] if last_completed else None
    from_step_name = last_completed["step_name"] if last_completed else None
    from_agent_name = None

    # Determine origin type
    if from_step_id is None:
        origin_type = "entry"

    else:
        prev_step = engine.step_map.get(from_step_id)

        if prev_step and prev_step.type == StepType.EVALUATOR:
            # Check if the evaluator explicitly routed to this step
            decision_key = f"_routing_decision_{from_step_id}"
            if decision_key in run.shared_state:
                decision = run.shared_state[decision_key]
                target = prev_step.route_map.get(decision)
                if target == step.id:
                    routing_reasoning = run.shared_state.get(f"_routing_reasoning_{from_step_id}")
                    if prev_step.agent_id:
                        from_agent_name = engine.agent_names.get(prev_step.agent_id)
                    return TransitionContext(
                        origin_type="evaluator",
                        execution_number=execution_number,
                        from_step_id=from_step_id,
                        from_step_name=from_step_name,
                        from_agent_name=from_agent_name or from_step_name,
                        routing_decision=decision,
                        routing_reasoning=routing_reasoning,
                    )

        elif prev_step and prev_step.type == StepType.HUMAN:
            # Find the output key that holds the human response
            human_key = prev_step.output_key or "human_response"
            return TransitionContext(
                origin_type="human_response",
                execution_number=execution_number,
                from_step_id=from_step_id,
                from_step_name=from_step_name,
                human_response_key=human_key,
            )

        elif prev_step and prev_step.type == StepType.LOOP:
            # Inside a loop body — get iteration metadata from shared_state
            iteration = run.shared_state.get("_loop_current_iteration")
            total = run.shared_state.get("_loop_total")
            return TransitionContext(
                origin_type="loop",
                execution_number=execution_number,
                from_step_id=from_step_id,
                from_step_name=from_step_name,
                loop_iteration=iteration,
                loop_total=total,
            )

        # Default: linear flow from previous step
        if prev_step and prev_step.agent_id:
            from_agent_name = engine.agent_names.get(prev_step.agent_id)
        origin_type = "linear"

    return TransitionContext(
        origin_type=origin_type,
        execution_number=execution_number,
        from_step_id=from_step_id,
        from_step_name=from_step_name,
        from_agent_name=from_agent_name,
    )


# ---------------------------------------------------------------------------
# Execution Memory
# ---------------------------------------------------------------------------

def build_execution_trace(events: list[dict]) -> dict:
    """
    Extract a structured trace from the SSE events emitted by run_agent_step().
    Keeps tool names/args/result-previews and the final response — NOT full outputs.
    """
    tool_calls: list[dict] = []
    tools_used: list[str] = []
    turn_count = 0
    final_output = ""

    for event in events:
        etype = event.get("type", "")

        if etype == "tool_call":
            name = event.get("tool_name") or event.get("tool") or ""
            args = event.get("tool_input") or event.get("arguments") or {}
            if name and name not in tools_used:
                tools_used.append(name)
            tool_calls.append({"name": name, "args": args})

        elif etype == "tool_result":
            # Attach result preview to the last recorded call for this tool
            result_raw = str(event.get("result") or event.get("output") or "")
            preview = result_raw[:300] + ("..." if len(result_raw) > 300 else "")
            if tool_calls:
                tool_calls[-1]["result_preview"] = preview

        elif etype in ("thinking", "agent_thinking"):
            turn_count += 1

        elif etype == "final":
            final_output = event.get("response", "")

    return {
        "tool_calls": tool_calls,
        "tools_used": tools_used,
        "turn_count": turn_count,
        "final_output": final_output,
    }


def store_execution_memory(
    run: "OrchestrationRun",
    step: "StepConfig",
    trace: dict,
    agent_name: str,
) -> None:
    """Append execution trace to shared_state under a namespaced key."""
    key = f"_exec_memory_{step.id}"
    history = run.shared_state.get(key)
    if not isinstance(history, list):
        history = []
    history.append({
        "execution": len(history) + 1,
        "agent": agent_name,
        "trace": trace,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    run.shared_state[key] = history


def get_execution_memory(run: "OrchestrationRun", step_id: str) -> list[dict]:
    """Return all recorded execution traces for a step (empty list if none)."""
    val = run.shared_state.get(f"_exec_memory_{step_id}")
    return val if isinstance(val, list) else []


# ---------------------------------------------------------------------------
# Workflow graph renderer
# ---------------------------------------------------------------------------

def build_workflow_graph_markdown(orch: "Orchestration", current_step_id: str) -> str:  # type: ignore[name-defined]
    """
    Build a compact markdown map of the orchestration graph.

    Traverses from entry_step_id, rendering top-level steps as numbered items.
    Branch steps inside parallel/loop blocks appear only as sub-bullets under
    their parent — never as top-level numbered steps.  Cycles are shown as
    "(retry)" references.

    Example output:
        ### WORKFLOW: Research Mid term stock
        Goal: Analyse and research mid term stocks

        #### Steps
        1. **Parallel Step** [parallel]
           ├─ Branch 1: Stock Analyser Alpha → `analysis_1`
           └─ Branch 2: Stock analyser beta → `analysis_2`   ← YOU ARE HERE
        2. **Merge Step** [merge] → `all_resources`
        3. **Final Verdict** [llm] → `final_result`
    """
    from core.models_orchestration import StepType

    step_map = {s.id: s for s in orch.steps}

    def _type_val(step) -> str:
        """Always return the plain string value (e.g. 'parallel'), never the enum repr."""
        t = step.type
        return t.value if hasattr(t, "value") else str(t)

    # ------------------------------------------------------------------
    # Walk the graph to determine top-level display order.
    # Branch steps (inside parallel/loop) are added to `seen` but NOT to
    # `ordered_ids` so they don't appear as numbered top-level steps.
    # ------------------------------------------------------------------
    ordered_ids: list[str] = []
    seen: set[str] = set()

    def _mark_branch_seen(step_id: str, stop_at: str | None) -> None:
        """Recursively mark branch body steps as seen without numbering them."""
        if not step_id or step_id in seen or step_id == stop_at or step_id not in step_map:
            return
        seen.add(step_id)
        _mark_branch_seen(step_map[step_id].next_step_id or "", stop_at)

    def _walk(step_id: str) -> None:
        if not step_id or step_id in seen or step_id not in step_map:
            return
        seen.add(step_id)
        ordered_ids.append(step_id)
        step = step_map[step_id]
        t = _type_val(step)

        if t == StepType.EVALUATOR.value and step.route_map:
            for target in step.route_map.values():
                if target and target not in seen:
                    _walk(target)

        elif t == StepType.PARALLEL.value and step.parallel_branches:
            # Mark every branch step as seen so they won't become top-level
            for branch in step.parallel_branches:
                for bid in branch:
                    _mark_branch_seen(bid, step.next_step_id)
            _walk(step.next_step_id or "")

        elif t == StepType.LOOP.value and step.loop_step_ids:
            for bid in step.loop_step_ids:
                _mark_branch_seen(bid, step.next_step_id)
            _walk(step.next_step_id or "")

        else:
            _walk(step.next_step_id or "")

    _walk(orch.entry_step_id)

    # Append anything not reachable from entry (shouldn't happen in valid graphs)
    for s in orch.steps:
        if s.id not in seen:
            ordered_ids.append(s.id)

    num: dict[str, int] = {sid: i + 1 for i, sid in enumerate(ordered_ids)}

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    lines: list[str] = [f"### WORKFLOW: {orch.name}"]
    if orch.description:
        lines.append(f"Goal: {orch.description}")
    lines.append("")
    lines.append("#### Steps")

    for sid in ordered_ids:
        step = step_map[sid]
        t = _type_val(step)
        here = "   ← YOU ARE HERE" if sid == current_step_id else ""
        out = f" → `{step.output_key}`" if step.output_key else ""

        if t == StepType.END.value:
            lines.append(f"{num[sid]}. **{step.name}** [END]{here}")
            continue

        lines.append(f"{num[sid]}. **{step.name}** [{t}]{out}{here}")

        # Evaluator: named routes with cycle detection
        if t == StepType.EVALUATOR.value and step.route_map:
            items = list(step.route_map.items())
            for idx, (decision, target_id) in enumerate(items):
                connector = "└─" if idx == len(items) - 1 else "├─"
                if target_id is None:
                    lines.append(f'   {connector} "{decision}" → [END]')
                elif target_id in num:
                    target_name = step_map[target_id].name
                    suffix = " (retry)" if num[target_id] <= num[sid] else ""
                    lines.append(f'   {connector} "{decision}" → {target_name}{suffix}')
                else:
                    lines.append(f'   {connector} "{decision}" → {target_id}')

        # Parallel: show each branch step with its output key
        elif t == StepType.PARALLEL.value and step.parallel_branches:
            all_branches = step.parallel_branches
            for b_idx, branch in enumerate(all_branches):
                connector = "└─" if b_idx == len(all_branches) - 1 else "├─"
                branch_parts = []
                for bid in branch:
                    if bid not in step_map:
                        continue
                    bs = step_map[bid]
                    bs_out = f" → `{bs.output_key}`" if bs.output_key else ""
                    bs_here = "   ← YOU ARE HERE" if bid == current_step_id else ""
                    branch_parts.append(f"{bs.name}{bs_out}{bs_here}")
                lines.append(f"   {connector} Branch {b_idx + 1}: {' → '.join(branch_parts)}")

        # Loop: show body with iteration count
        elif t == StepType.LOOP.value and step.loop_step_ids:
            body_names = " → ".join(
                step_map[bid].name for bid in step.loop_step_ids if bid in step_map
            )
            lines.append(f"   └─ body ({step.loop_count}×): {body_names}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _format_tool_calls(tool_calls: list[dict]) -> str:
    """Format tool call list into a compact readable block."""
    lines = []
    for tc in tool_calls:
        name = tc.get("name", "?")
        args = tc.get("args", {})
        # Show first arg value or stringify compactly
        if isinstance(args, dict) and args:
            first_key, first_val = next(iter(args.items()))
            arg_str = f'{first_key}="{str(first_val)[:80]}"'
            if len(args) > 1:
                arg_str += f" (+{len(args)-1} more)"
        else:
            arg_str = str(args)[:80]
        preview = tc.get("result_preview", "")
        line = f"  - {name}({arg_str})"
        if preview:
            line += f" → {preview[:120]}"
        lines.append(line)
    return "\n".join(lines)


def _format_context_value(
    key: str,
    val,
    label: str,
    max_chars: int = 5000,
) -> str:
    """Format a single shared_state value for inclusion in the prompt."""
    # List values from loop/parallel accumulation
    if isinstance(val, list) and val and isinstance(val[0], dict) and "result" in val[0]:
        parts = []
        for entry in val:
            iteration = entry.get("iteration", entry.get("run", ""))
            agent = entry.get("agent", "")
            result_str = str(entry.get("result", ""))
            if len(result_str) > max_chars:
                from .summarizer import smart_truncate
                result_str = smart_truncate(result_str, max_chars)
            iter_label = f" (Iteration {iteration})" if iteration else ""
            source = f"{agent} → {key}{iter_label}" if agent else f"{key}{iter_label}"
            parts.append(f"### [{source}]\n{result_str}")
        return "\n\n".join(parts)

    val_str = str(val)
    if len(val_str) > max_chars:
        from .summarizer import smart_truncate
        val_str = smart_truncate(val_str, max_chars)
    return f"### [{label}]\n{val_str}"


def build_origin_aware_context(
    step: "StepConfig",
    run: "OrchestrationRun",
    engine: "OrchestrationEngine",
    transition: TransitionContext,
) -> tuple[str, str]:
    """
    Build (prompt, system_prompt_extra) for an agent/tool/llm step using
    the structured, origin-aware format.

    Returns two strings:
      prompt              — the full user-turn message to send to the LLM
      system_prompt_extra — short orchestration-awareness block to append to
                            the agent's system prompt (can be empty string)
    """
    import re
    sections: list[str] = []

    # ------------------------------------------------------------------
    # Section: ROLE
    # ------------------------------------------------------------------
    orch_name = engine.orch.name
    step_name = step.name
    output_key = step.output_key or "(no output key set)"

    role_lines = [
        f"## YOUR ROLE IN THIS WORKFLOW",
        f"Workflow: \"{orch_name}\"",
        f"Step: \"{step_name}\"",
        f"Your output will be stored as: \"{output_key}\"",
    ]

    if transition.origin_type == "entry":
        role_lines.append("You are the first step — no prior steps have run.")
    elif transition.origin_type == "linear":
        prev = transition.from_step_name or transition.from_step_id or "previous step"
        agent = transition.from_agent_name
        invoked_by = f"\"{prev}\"" + (f" (agent: {agent})" if agent else "")
        role_lines.append(f"Invoked after: {invoked_by} (linear flow).")
    elif transition.origin_type == "evaluator":
        role_lines.append(
            f"This is execution #{transition.execution_number} of this step."
        )
        role_lines.append(
            f"You were sent back by evaluator \"{transition.from_step_name}\"."
        )
    elif transition.origin_type == "loop":
        iter_str = (
            f"Loop iteration {transition.loop_iteration} of {transition.loop_total}"
            if transition.loop_iteration and transition.loop_total
            else "Loop iteration"
        )
        role_lines.append(f"{iter_str}. Invoked by loop step \"{transition.from_step_name}\".")
    elif transition.origin_type == "human_response":
        role_lines.append(
            f"Invoked after human input step \"{transition.from_step_name}\"."
        )

    sections.append("\n".join(role_lines))

    # ------------------------------------------------------------------
    # Section: EVALUATOR FEEDBACK (only on evaluator re-invocation)
    # ------------------------------------------------------------------
    if transition.origin_type == "evaluator" and (
        transition.routing_decision or transition.routing_reasoning
    ):
        feedback_lines = ["## EVALUATOR FEEDBACK"]
        if transition.routing_decision:
            feedback_lines.append(f"Decision: \"{transition.routing_decision}\"")
        if transition.routing_reasoning:
            feedback_lines.append(f"Reason: {transition.routing_reasoning}")

        # Previous output summary
        if step.output_key and step.output_key in run.shared_state:
            prev_out = str(run.shared_state[step.output_key])
            if len(prev_out) > 2000:
                from .summarizer import smart_truncate
                prev_out = smart_truncate(prev_out, 2000)
            feedback_lines.append(f"\n### Your previous output\n{prev_out}")

        sections.append("\n".join(feedback_lines))

    # ------------------------------------------------------------------
    # Section: YOUR PREVIOUS WORK (on any re-invocation)
    # ------------------------------------------------------------------
    if transition.execution_number > 1:
        memory = get_execution_memory(run, step.id)
        if memory:
            last = memory[-1]
            trace = last.get("trace", {})
            prev_work_lines = ["## YOUR PREVIOUS WORK ON THIS TASK"]
            tool_calls = trace.get("tool_calls", [])
            if tool_calls:
                prev_work_lines.append(
                    f"Tools used ({len(tool_calls)} calls):\n"
                    + _format_tool_calls(tool_calls)
                )
            else:
                tools_used = trace.get("tools_used", [])
                if tools_used:
                    prev_work_lines.append(f"Tools used: {', '.join(tools_used)}")
                else:
                    prev_work_lines.append("No tools were used.")
            sections.append("\n".join(prev_work_lines))

    # ------------------------------------------------------------------
    # Section: HUMAN INPUT (when invoked after a human step)
    # ------------------------------------------------------------------
    if transition.origin_type == "human_response" and transition.human_response_key:
        hkey = transition.human_response_key
        human_val = run.shared_state.get(hkey)
        if human_val:
            sections.append(
                f"## HUMAN INPUT\n"
                f"The user provided the following response:\n{human_val}"
            )

    # ------------------------------------------------------------------
    # Section: PREVIOUS ITERATIONS (loop context)
    # ------------------------------------------------------------------
    if transition.origin_type == "loop" and step.output_key:
        loop_key = f"_loop_{step.output_key}"
        loop_results = run.shared_state.get(loop_key, [])
        if loop_results:
            iter_lines = ["## PREVIOUS ITERATIONS"]
            for entry in loop_results[-5:]:  # last 5 to keep it manageable
                it = entry.get("iteration", "?")
                res = str(entry.get("result", ""))[:200]
                iter_lines.append(f"Iteration {it}: {res}")
            sections.append("\n".join(iter_lines))

    # ------------------------------------------------------------------
    # Section: CONTEXT FROM PREVIOUS STEPS
    # ------------------------------------------------------------------
    context_parts = []

    # Always include user_input unless explicitly in input_keys
    if "user_input" in run.shared_state and "user_input" not in (step.input_keys or []):
        context_parts.append(f"### [user_input]\n{run.shared_state['user_input']}")

    # Human response keys (always inject unless already listed)
    human_keys = {"human_response"}
    for s in engine.step_map.values():
        if s.type and s.type.value == "human" and s.output_key:
            human_keys.add(s.output_key)
    for hkey in sorted(human_keys):
        if (
            hkey in run.shared_state
            and hkey not in (step.input_keys or [])
            and hkey != "user_input"
        ):
            val = str(run.shared_state[hkey])
            if len(val) > 3000:
                from .summarizer import smart_truncate
                val = smart_truncate(val, 3000)
            context_parts.append(f"### [{hkey}]\n{val}")

    # Explicitly declared input_keys
    for key in (step.input_keys or []):
        if key not in run.shared_state:
            continue
        val = run.shared_state[key]
        label = key
        producer = next(
            (s for s in engine.step_map.values() if s.output_key == key), None
        )
        if producer and producer.agent_id and producer.agent_id in engine.agent_names:
            label = f"{engine.agent_names[producer.agent_id]} \u2192 {key}"
        context_parts.append(_format_context_value(key, val, label))

    if context_parts:
        sections.append("## CONTEXT FROM PREVIOUS STEPS\n" + "\n\n".join(context_parts))

    # ------------------------------------------------------------------
    # Section: TASK
    # ------------------------------------------------------------------
    prompt_template = step.prompt_template or run.shared_state.get("user_input", "")

    # Replace {state.key} references
    def replace_ref(match):
        k = match.group(1)
        return str(run.shared_state.get(k, f"{{state.{k}}}"))

    task_text = re.sub(r"\{state\.(\w+)\}", replace_ref, prompt_template)

    task_header = "## TASK (REVISION)" if transition.origin_type == "evaluator" else "## TASK"
    task_suffix = ""
    if transition.origin_type == "evaluator" and transition.routing_reasoning:
        task_suffix = "\n\nAddress the evaluator's feedback above in your revised output."
    elif transition.origin_type == "human_response":
        task_suffix = "\n\nIncorporate the human's input above."

    sections.append(f"{task_header}\n{task_text}{task_suffix}")

    # ------------------------------------------------------------------
    # Assemble final prompt
    # ------------------------------------------------------------------
    prompt = "\n\n---\n\n".join(sections)

    # ------------------------------------------------------------------
    # System prompt addition — workflow graph + step position
    # ------------------------------------------------------------------
    graph_md = build_workflow_graph_markdown(engine.orch, step.id)
    sys_lines = [
        graph_md,
        "",
        f"You are currently executing step **\"{step_name}\"** (execution #{transition.execution_number}).",
        f"Your output will be stored as: `{output_key}`",
    ]
    if transition.origin_type == "evaluator":
        sys_lines.append(
            f"You are revising your previous output based on evaluator feedback "
            f"(\"{transition.routing_decision}\")."
        )
    system_prompt_extra = "\n".join(sys_lines)

    return prompt, system_prompt_extra
