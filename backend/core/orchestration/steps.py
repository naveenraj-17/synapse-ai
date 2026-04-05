"""
Step executors for each orchestration step type.
Each executor is an async generator that yields SSE-compatible events.
"""
import asyncio
import datetime
import json
import re
import subprocess
import sys
import time
from typing import AsyncGenerator, TYPE_CHECKING

import anyio

from core.models_orchestration import StepConfig, StepType, OrchestrationRun

if TYPE_CHECKING:
    from .engine import OrchestrationEngine


def _datetime_context() -> str:
    """Return a markdown block with the current date, time, and timezone."""
    now = datetime.datetime.now().astimezone()
    tz_name = now.strftime("%Z") or str(now.tzinfo)
    return (
        "### CURRENT DATE & TIME CONTEXT\n"
        f"**Current Date:** {now.strftime('%A, %B %d, %Y')}\n"
        f"**Current Time:** {now.strftime('%I:%M %p')}\n"
        f"**Timezone:** {tz_name}\n"
    )


class AgentStepExecutor:
    """Run a sub-agent's ReAct loop. Reuses the existing engine."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        from core.react_engine import run_agent_step
        from core.agent_logger import AgentLogger
        print(f"DEBUG AGENT EXEC: agent_id={step.agent_id} step={step.id}", flush=True)

        from .context import build_origin_aware_context
        transition = getattr(engine, "current_transition", None)
        if transition is None:
            from .context import TransitionContext
            transition = TransitionContext(origin_type="entry", execution_number=1)
        prompt, system_prompt_extra = build_origin_aware_context(
            step, run, engine, transition
        )

        # Emit prompt for the orchestration logger (filtered out before SSE)
        yield {"type": "_log_prompt", "orch_step_id": step.id, "prompt": prompt, "system_prompt_extra": system_prompt_extra}

        agent_id = step.agent_id or "default"
        agent_name = engine.agent_names.get(agent_id, agent_id)
        # Group sub-agent logs under the same session as the orchestration
        session_id = run.session_id or f"orch_{run.run_id}"
        agent_log = AgentLogger(
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
            source=f"orchestration:{run.run_id}",
            user_message=prompt,
        )
        # Log the prompt in the agent log too
        agent_log.log_event({"type": "_log_prompt", "prompt": prompt})

        final_response = None
        _log_status = "completed"
        execution_events: list[dict] = []
        try:
            async for event in run_agent_step(
                message=prompt,
                agent_id=step.agent_id,
                session_id=session_id,
                server_module=engine.server_module,
                max_turns=step.max_turns,
                allowed_tools_override=step.allowed_tools,
                source="orchestration",
                run_id=run.run_id,
                system_prompt_extra=system_prompt_extra,
            ):
                execution_events.append(event)
                agent_log.log_event(event)
                yield {**event, "orch_step_id": step.id, "step_name": step.name}
                if event.get("type") == "final":
                    final_response = event.get("response", "")
        except Exception:
            _log_status = "error"
            raise
        finally:
            agent_log.run_end(_log_status)

        if step.output_key and final_response:
            run.shared_state[step.output_key] = final_response

        # Store execution trace for memory across re-invocations
        from .context import build_execution_trace, store_execution_memory
        trace = build_execution_trace(execution_events)
        store_execution_memory(run, step, trace, agent_name)


class ToolStepExecutor:
    """Single forced tool call with ReAct retry loop.

    Constrains run_agent_step to exactly one tool. The LLM must call that tool —
    if it gets the arguments wrong, the ReAct loop retries (up to max_turns).
    No agent_id required — uses the active/default agent for model/provider settings.
    """

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        from core.react_engine import run_agent_step
        from core.agent_logger import AgentLogger

        if not step.forced_tool:
            yield {"type": "step_warning", "orch_step_id": step.id,
                   "message": f"No tool configured for TOOL step '{step.name}'"}
            return

        from .context import build_origin_aware_context
        transition = getattr(engine, "current_transition", None)
        if transition is None:
            from .context import TransitionContext
            transition = TransitionContext(origin_type="entry", execution_number=1)
        prompt, system_prompt_extra = build_origin_aware_context(step, run, engine, transition)

        yield {"type": "_log_prompt", "orch_step_id": step.id, "prompt": prompt, "system_prompt_extra": system_prompt_extra}

        agent_id = step.agent_id
        session_id = run.session_id or f"orch_{run.run_id}"

        agent_log = AgentLogger(
            agent_id=agent_id or "tool_step",
            agent_name=engine.agent_names.get(agent_id, step.name) if agent_id else step.name,
            session_id=session_id,
            source=f"orchestration:{run.run_id}",
            user_message=prompt,
        )
        agent_log.log_event({"type": "_log_prompt", "prompt": prompt})

        final_response = None
        _log_status = "completed"
        try:
            async for event in run_agent_step(
                message=prompt,
                agent_id=agent_id,
                session_id=session_id,
                server_module=engine.server_module,
                max_turns=step.max_turns,
                allowed_tools_override=[step.forced_tool],
                source="orchestration",
                run_id=run.run_id,
                system_prompt_extra=system_prompt_extra,
            ):
                agent_log.log_event(event)
                yield {**event, "orch_step_id": step.id, "step_name": step.name}
                if event.get("type") == "final":
                    final_response = event.get("response", "")
        except Exception:
            _log_status = "error"
            raise
        finally:
            agent_log.run_end(_log_status)

        if step.output_key and final_response:
            run.shared_state[step.output_key] = final_response


class EvaluatorStepExecutor:
    """Pure routing node — no agent. Makes a single LLM call using
    evaluator_prompt + route_descriptions + context from input_keys
    to decide which route to take."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        from core.llm_providers import generate_response as llm_generate_response
        from core.config import load_settings

        if not step.route_map:
            yield {"type": "step_warning", "orch_step_id": step.id, "message": "No routes defined"}
            return

        # Build context from input_keys
        context_parts = []
        for key in (step.input_keys or []):
            if key not in run.shared_state:
                continue
            val = run.shared_state[key]
            # Find producer for attribution
            label = key
            producer = next((s for s in engine.step_map.values() if s.output_key == key), None)
            if producer and producer.agent_id and producer.agent_id in engine.agent_names:
                label = f"{engine.agent_names[producer.agent_id]} → {key}"

            val_str = str(val)
            context_parts.append(f"[{label}]:\n{val_str}")

        context_block = "\n\n".join(context_parts) if context_parts else "(no context available)"

        # Build route descriptions
        route_lines = []
        labels = list(step.route_map.keys())
        for label_name, target_id in step.route_map.items():
            custom_desc = step.route_descriptions.get(label_name, "")
            if custom_desc:
                route_lines.append(f'  - "{label_name}": {custom_desc}')
            elif target_id is None:
                route_lines.append(f'  - "{label_name}": End the orchestration')
            else:
                target_step = engine.step_map.get(target_id)
                target_name = target_step.name if target_step else target_id
                route_lines.append(f'  - "{label_name}": Route to {target_name}')
        routes_text = "\n".join(route_lines)

        evaluator_instructions = ""
        if step.evaluator_prompt:
            evaluator_instructions = f"EVALUATOR INSTRUCTIONS:\n{step.evaluator_prompt}\n\n"

        prompt = (
            f"{evaluator_instructions}"
            f"{_datetime_context()}\n"
            f"Based on the context below, decide which route to take.\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"AVAILABLE ROUTES:\n{routes_text}\n\n"
            f"Respond with ONLY a JSON object: {{\"tool\": \"route_<label>\", \"arguments\": {{\"reasoning\": \"your reason\"}}}}\n"
            f"Valid labels: {labels}"
        )

        # Emit evaluator prompt for the logger
        yield {"type": "_log_prompt", "orch_step_id": step.id, "prompt": prompt}

        yield {"type": "thinking", "orch_step_id": step.id, "message": f"Evaluator deciding route..."}

        settings = load_settings()
        routing_decision = None
        # Per-step model override for evaluators.
        # Treat None, empty string, or "default" as "use the global default model".
        _step_model = step.model if (step.model and step.model.strip().lower() not in ("", "default")) else None
        eval_model = _step_model if _step_model else settings.get("model", "mistral")
        from core.llm_providers import detect_mode_from_model
        eval_mode = detect_mode_from_model(eval_model)
        try:
            response = await llm_generate_response(
                prompt_msg=prompt,
                sys_prompt="You are a routing decision maker. Output ONLY valid JSON.",
                mode=eval_mode,
                current_model=eval_model,
                current_settings=settings,
                session_id=run.session_id,
                agent_id=step.agent_id or "evaluator",
                source="orchestration",
                run_id=run.run_id,
            )
            print(f"DEBUG: 🔀 Evaluator LLM response: {response}")

            # Emit evaluator LLM response for the logger
            yield {"type": "_log_evaluator", "orch_step_id": step.id, "prompt": prompt, "llm_response": response}

            from core.react_engine import parse_tool_call
            tool_call, _ = parse_tool_call(response)
            if tool_call:
                tool_name = tool_call.get("tool") or tool_call.get("name", "")
                if tool_name in {f"route_{l}" for l in labels}:
                    routing_decision = {
                        "type": "routing_decision",
                        "tool_name": tool_name,
                        "arguments": tool_call.get("arguments", {}),
                    }
        except Exception as e:
            # LLM errors must propagate to stop orchestration
            from core.llm_providers import LLMError
            if isinstance(e, LLMError):
                print(f"DEBUG: ❌ Evaluator LLM failed — stopping orchestration: {e}", flush=True)
                raise
            print(f"DEBUG: Evaluator routing call failed: {e}")

        # Fallback: pick the first route
        if not routing_decision:
            fallback_label = labels[0] if labels else None
            if fallback_label:
                print(f"DEBUG: Evaluator falling back to first route: {fallback_label}")
                routing_decision = {
                    "type": "routing_decision",
                    "tool_name": f"route_{fallback_label}",
                    "arguments": {"reasoning": "Fallback — LLM did not return a valid routing decision"},
                }

        if routing_decision:
            print(f"routing decision")
            yield {**routing_decision, "orch_step_id": step.id}
            tool_name = routing_decision.get("tool_name", "")
            label = tool_name.replace("route_", "", 1) if tool_name.startswith("route_") else tool_name
            run.shared_state[f"_routing_decision_{step.id}"] = label
            run.shared_state[f"_routing_reasoning_{step.id}"] = routing_decision.get("arguments", {}).get("reasoning", "")

            # Store evaluator output if output_key is configured
            if step.output_key:
                run.shared_state[step.output_key] = f"Route: {label} — {routing_decision.get('arguments', {}).get('reasoning', '')}"


class ParallelStepExecutor:
    """Run multiple branches.

    Each branch entry in ``parallel_branches`` can be:
      - A single entry-point step ID  → executor auto-follows ``next_step_id`` chain
      - Multiple step IDs             → executor runs them in that explicit order

    A branch chain stops when a step has no ``next_step_id``, or its ``next_step_id``
    equals the parallel node's own convergence point (``step.next_step_id``).

    NOTE: Branches run sequentially (not with asyncio.gather) because agents
    share resources that are not concurrency-safe — notably MCP server
    connections and single-instance tools like the Playwright browser.
    True parallel execution would require per-branch tool isolation.
    """

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        branches = step.parallel_branches
        print(f"DEBUG PARALLEL: ▶ step='{step.id}' branches={len(branches)} convergence='{step.next_step_id}'", flush=True)
        if not branches:
            yield {"type": "step_warning", "orch_step_id": step.id, "message": "No branches defined"}
            return

        convergence_id = step.next_step_id  # e.g. the Merge node

        def resolve_branch_chain(branch: list[str]) -> list[str]:
            """If the branch only lists an entry point, walk next_step_id to build the full chain."""
            if len(branch) != 1:
                return branch  # explicit chain — use as-is
            chain = [branch[0]]
            visited = {branch[0]}
            current = branch[0]
            while True:
                sub = engine.step_map.get(current)
                if not sub or not sub.next_step_id:
                    break
                nxt = sub.next_step_id
                if nxt == convergence_id or nxt in visited:
                    break
                chain.append(nxt)
                visited.add(nxt)
                current = nxt
            return chain

        resolved_branches = [resolve_branch_chain(b) for b in branches]

        yield {"type": "parallel_start", "orch_step_id": step.id, "branch_count": len(resolved_branches)}

        # Run branches sequentially to avoid MCP/browser resource contention
        for branch_index, branch_step_ids in enumerate(resolved_branches):
            # Checkpoint between branches — give MCP background tasks time
            await anyio.sleep(0)

            print(f"DEBUG PARALLEL: ├─ branch {branch_index}/{len(resolved_branches)} steps={branch_step_ids}", flush=True)
            yield {"type": "branch_start", "orch_step_id": step.id,
                   "branch_index": branch_index, "branch_count": len(resolved_branches)}

            for sid in branch_step_ids:
                sub_step = engine.step_map.get(sid)
                if not sub_step:
                    yield {"type": "step_warning", "orch_step_id": sid,
                           "message": f"Step {sid} not found in branch {branch_index}"}
                    continue
                executor = engine.executors.get(sub_step.type)
                if not executor:
                    yield {"type": "step_error", "orch_step_id": sid,
                           "error": f"No executor for {sub_step.type}"}
                    continue

                step_start = time.time()
                sub_timeout = sub_step.timeout_seconds or 300
                print(f"DEBUG PARALLEL:   ▶ sub-step '{sub_step.name}' ({sub_step.id}) timeout={sub_timeout}s", flush=True)
                yield {"type": "step_start", "orch_step_id": sub_step.id,
                       "step_name": sub_step.name, "step_type": sub_step.type.value}

                try:
                    with anyio.fail_after(sub_timeout):
                        async for event in executor.execute(sub_step, run, engine):
                            yield event
                except TimeoutError:
                    duration = round(time.time() - step_start, 2)
                    print(f"DEBUG PARALLEL: ⏱ Step '{sub_step.name}' timed out after {sub_timeout}s in branch {branch_index}", flush=True)
                    run.step_history.append({
                        "step_id": sub_step.id, "step_name": sub_step.name,
                        "step_type": sub_step.type.value, "status": "failed",
                        "error": f"Timed out after {sub_timeout}s",
                    })
                    yield {"type": "step_error", "orch_step_id": sub_step.id,
                           "error": f"Step '{sub_step.name}' timed out after {sub_timeout}s"}
                    continue

                duration = round(time.time() - step_start, 2)
                print(f"DEBUG PARALLEL:   ✓ sub-step '{sub_step.name}' done in {duration}s", flush=True)
                run.step_history.append({
                    "step_id": sub_step.id, "step_name": sub_step.name,
                    "step_type": sub_step.type.value, "status": "completed",
                    "duration_seconds": duration, "output_key": sub_step.output_key,
                })
                yield {"type": "step_complete", "orch_step_id": sub_step.id,
                       "step_name": sub_step.name, "duration_seconds": duration}

        print(f"DEBUG PARALLEL: ✅ all {len(resolved_branches)} branches complete", flush=True)
        yield {"type": "parallel_complete", "orch_step_id": step.id, "branch_count": len(resolved_branches)}


class MergeStepExecutor:
    """Combine outputs from parallel branches into a single result."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        # Use an ordered list of (display_label, value) pairs so that two steps
        # sharing the same agent_id (and thus the same agent name) never
        # overwrite each other.  The unique key is always the step ID; the
        # display label is "StepName (step_id)" so it stays human-readable.
        entries: list[tuple[str, object]] = []
        for key in step.input_keys:
            if key not in run.shared_state:
                continue

            # Locate the step that produced this output_key
            producer = next(
                (s for s in engine.orch.steps if s.output_key == key), None
            )

            # Build a human-readable label anchored to the *step*, not the agent.
            # Pattern: "StepName (step_id)"  e.g. "NSE Stock Alpha Data (step_ixjrdrk)"
            if producer:
                step_label = f"{producer.name} ({producer.id})"
            else:
                step_label = key

            entries.append((step_label, run.shared_state[key]))

        if step.merge_strategy == "concat":
            merged = "\n\n".join(f"[{label}]:\n{value}" for label, value in entries)
        elif step.merge_strategy == "dict":
            # Use step_label as key — guaranteed unique because step IDs are unique
            merged = {label: value for label, value in entries}
        else:  # "list" (default)
            merged = [{"source": label, "data": value} for label, value in entries]

        if step.output_key:
            run.shared_state[step.output_key] = merged

        yield {
            "type": "merge_complete", "orch_step_id": step.id,
            "input_count": len(entries), "strategy": step.merge_strategy,
        }


class LoopStepExecutor:
    """Run body steps N times sequentially, accumulating results."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        loop_count = max(1, step.loop_count)
        body_ids = step.loop_step_ids
        print(f"DEBUG LOOP: ▶ step='{step.id}' body_ids={body_ids} loop_count={loop_count}", flush=True)

        if not body_ids:
            yield {"type": "step_warning", "orch_step_id": step.id, "message": "No loop body steps defined"}
            return

        for iteration in range(1, loop_count + 1):
            yield {
                "type": "loop_iteration", "orch_step_id": step.id,
                "iteration": iteration, "total": loop_count,
            }

            for sid in body_ids:
                sub_step = engine.step_map.get(sid)
                if not sub_step:
                    yield {"type": "step_warning", "orch_step_id": step.id,
                           "message": f"Loop body step {sid} not found"}
                    continue

                executor = engine.executors.get(sub_step.type)
                if not executor:
                    yield {"type": "step_error", "orch_step_id": sid,
                           "error": f"No executor for {sub_step.type}"}
                    continue

                step_start = time.time()
                sub_timeout = sub_step.timeout_seconds or 300
                yield {"type": "step_start", "orch_step_id": sub_step.id,
                       "step_name": sub_step.name, "step_type": sub_step.type.value}

                try:
                    with anyio.fail_after(sub_timeout):
                        async for event in executor.execute(sub_step, run, engine):
                            # Human input within loop body — propagate up
                            if event.get("type") == "human_input_required":
                                yield event
                                return
                            yield event
                except TimeoutError:
                    duration = round(time.time() - step_start, 2)
                    print(f"DEBUG LOOP: ⏱ Step '{sub_step.name}' timed out after {sub_timeout}s (iteration {iteration})", flush=True)
                    run.step_history.append({
                        "step_id": sub_step.id, "step_name": sub_step.name,
                        "step_type": sub_step.type.value, "status": "failed",
                        "error": f"Timed out after {sub_timeout}s",
                    })
                    yield {"type": "step_error", "orch_step_id": sub_step.id,
                           "error": f"Step '{sub_step.name}' timed out after {sub_timeout}s"}
                    continue

                duration = round(time.time() - step_start, 2)
                run.step_history.append({
                    "step_id": sub_step.id, "step_name": sub_step.name,
                    "step_type": sub_step.type.value, "status": "completed",
                    "duration_seconds": duration, "output_key": sub_step.output_key,
                })
                yield {"type": "step_complete", "orch_step_id": sub_step.id,
                       "step_name": sub_step.name, "duration_seconds": duration}

            # After each iteration, accumulate results from body steps
            for sid in body_ids:
                sub_step = engine.step_map.get(sid)
                if not sub_step or not sub_step.output_key:
                    continue
                if sub_step.output_key not in run.shared_state:
                    continue

                acc_key = f"_loop_{sub_step.output_key}"
                agent_name = engine.agent_names.get(sub_step.agent_id, sub_step.name) if sub_step.agent_id else sub_step.name
                if acc_key not in run.shared_state:
                    run.shared_state[acc_key] = []
                run.shared_state[acc_key].append({
                    "iteration": iteration,
                    "agent": agent_name,
                    "result": run.shared_state[sub_step.output_key],
                })

        # After all iterations, promote accumulated results to output keys
        for sid in body_ids:
            sub_step = engine.step_map.get(sid)
            if not sub_step or not sub_step.output_key:
                continue
            acc_key = f"_loop_{sub_step.output_key}"
            if acc_key in run.shared_state:
                run.shared_state[sub_step.output_key] = run.shared_state.pop(acc_key)

        # Store loop's own output if configured
        if step.output_key:
            # Collect all body outputs as summary
            summary = {}
            for sid in body_ids:
                sub_step = engine.step_map.get(sid)
                if sub_step and sub_step.output_key and sub_step.output_key in run.shared_state:
                    summary[sub_step.name] = run.shared_state[sub_step.output_key]
            run.shared_state[step.output_key] = summary

        yield {"type": "loop_complete", "orch_step_id": step.id,
               "iterations_completed": loop_count}


class HumanStepExecutor:
    """Pause execution and request human input.

    If the step has a human_channel_id configured, the prompt is also sent
    to that messaging channel. Whichever responds first — the messaging app
    or the browser UI — wins. The later response is silently discarded.
    """

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        prompt = step.human_prompt or "Please provide input to continue."
        prompt = re.sub(
            r"\{state\.(\w+)\}",
            lambda m: str(run.shared_state.get(m.group(1), f"{{state.{m.group(1)}}}")),
            prompt,
        )

        run.human_prompt = prompt
        run.human_fields = step.human_fields

        # Gather recent agent output from shared state for display context
        agent_context = None
        for key in (step.input_keys or []):
            if key in run.shared_state and run.shared_state[key]:
                agent_context = str(run.shared_state[key])
                break
        # Fallback: find the last output from step history
        if not agent_context:
            for h in reversed(run.step_history):
                okey = h.get("output_key")
                if okey and okey in run.shared_state:
                    agent_context = str(run.shared_state[okey])
                    break

        # If a messaging channel is configured, arm a Future so the messaging
        # adapter can resolve it when the user replies there.
        channel_id = step.human_channel_id
        if channel_id:
            messaging_manager = getattr(
                getattr(engine.server_module, "app", None),
                "state", None,
            )
            if messaging_manager:
                messaging_manager = getattr(messaging_manager, "messaging_manager", None)
            if messaging_manager:
                asyncio.create_task(
                    messaging_manager.wait_for_human_input(
                        run_id=run.run_id,
                        step_id=step.id,
                        channel_id=channel_id,
                        prompt=prompt,
                        timeout=step.human_timeout_seconds,
                    )
                )

        yield {
            "type": "human_input_required",
            "orch_step_id": step.id,
            "prompt": prompt,
            "fields": step.human_fields,
            "run_id": run.run_id,
            "agent_context": agent_context,
            "channel_id": channel_id,  # frontend can show which channel was notified
        }


class TransformStepExecutor:
    """Run sandboxed Python code to transform shared state."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        code = step.transform_code
        if not code:
            yield {"type": "step_warning", "orch_step_id": step.id, "message": "No transform code provided"}
            return

        yield {"type": "_log_prompt", "orch_step_id": step.id, "prompt": f"[Transform Code]\n{code}"}

        try:
            result = await self._run_sandboxed(code, run.shared_state, timeout=step.timeout_seconds)

            if step.output_key and result is not None:
                run.shared_state[step.output_key] = result

            yield {
                "type": "transform_result",
                "orch_step_id": step.id,
                "result": str(result) if result is not None else None,
            }
        except Exception as e:
            yield {"type": "step_error", "orch_step_id": step.id, "error": f"Transform error: {e}"}

    async def _run_sandboxed(self, code: str, state: dict, timeout: int = 30):
        """Run Python code in a subprocess with resource limits."""
        wrapper = f"""
import json, sys, math

state = json.loads(sys.stdin.read())
result = None

{code}

if result is not None:
    print(json.dumps({{"result": result}}, default=str))
else:
    print(json.dumps({{"result": None}}))
"""
        loop = asyncio.get_event_loop()

        def _run():
            proc = subprocess.run(
                [sys.executable, "-c", wrapper],
                input=json.dumps(state, default=str),
                capture_output=True,
                text=True,
                timeout=min(timeout, 60),
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Transform failed: {proc.stderr}")
            try:
                output = json.loads(proc.stdout)
                return output.get("result")
            except json.JSONDecodeError:
                return proc.stdout.strip() if proc.stdout.strip() else None

        return await loop.run_in_executor(None, _run)


class LLMStepExecutor:
    """Single direct LLM call — no agent, no tools, no routing.

    Useful for inline summaries, rewrites, or lightweight reasoning
    between heavier agent steps.
    """

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        from core.llm_providers import generate_response as llm_generate, detect_mode_from_model
        from core.config import load_settings

        from .context import build_origin_aware_context
        transition = getattr(engine, "current_transition", None)
        if transition is None:
            from .context import TransitionContext
            transition = TransitionContext(origin_type="entry", execution_number=1)
        prompt, system_prompt_extra = build_origin_aware_context(step, run, engine, transition)

        yield {"type": "_log_prompt", "orch_step_id": step.id, "prompt": prompt, "system_prompt_extra": system_prompt_extra}
        yield {
            "type": "thinking",
            "orch_step_id": step.id,
            "step_name": step.name,
            "message": f"LLM step '{step.name}' — calling model...",
        }

        settings = load_settings()
        # Treat None, empty string, or "default" as "use the global default model".
        _step_model = step.model if (step.model and step.model.strip().lower() not in ("", "default")) else None
        model = _step_model if _step_model else settings.get("model", "mistral")
        mode = detect_mode_from_model(model)

        try:
            response = await llm_generate(
                prompt_msg=prompt,
                sys_prompt=f"You are a helpful assistant. Be concise and accurate.\n\n{_datetime_context()}",
                mode=mode,
                current_model=model,
                current_settings=settings,
                session_id=run.session_id,
                agent_id=step.agent_id or "llm_step",
                source="orchestration",
                run_id=run.run_id,
            )
        except Exception as e:
            from core.llm_providers import LLMError
            if isinstance(e, LLMError):
                raise
            raise RuntimeError(f"LLM step '{step.name}' failed: {e}") from e

        if step.output_key:
            run.shared_state[step.output_key] = response

        yield {
            "type": "final",
            "orch_step_id": step.id,
            "step_name": step.name,
            "response": response,
        }


class EndStepExecutor:
    """Terminate the orchestration."""

    async def execute(
        self, step: StepConfig, run: OrchestrationRun, engine: "OrchestrationEngine"
    ) -> AsyncGenerator[dict, None]:
        run.status = "completed"
        yield {"type": "orchestration_end", "orch_step_id": step.id}


# Registry of all step executors
STEP_EXECUTORS = {
    StepType.AGENT: AgentStepExecutor(),
    StepType.LLM: LLMStepExecutor(),
    StepType.TOOL: ToolStepExecutor(),
    StepType.EVALUATOR: EvaluatorStepExecutor(),
    StepType.PARALLEL: ParallelStepExecutor(),
    StepType.MERGE: MergeStepExecutor(),
    StepType.LOOP: LoopStepExecutor(),
    StepType.HUMAN: HumanStepExecutor(),
    StepType.TRANSFORM: TransformStepExecutor(),
    StepType.END: EndStepExecutor(),
}
