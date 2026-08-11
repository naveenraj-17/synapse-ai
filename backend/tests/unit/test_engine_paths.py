"""
Extra engine paths: run_agent_step orchestration parameters and additional step
executor branches (merge strategies, if/else eval error, switch output_key,
extract_json multiple objects, print empty)."""
import types

import pytest

from _fakes import seed as S


def _server():
    return types.SimpleNamespace(agent_sessions={}, memory_store=None, tool_router={})


async def _run(orch_dict, fake_llm=None, script=None, initial_state=None):
    from core.models_orchestration import Orchestration
    from core.orchestration.engine import OrchestrationEngine
    if fake_llm is not None and script is not None:
        fake_llm.script(script)
    engine = OrchestrationEngine(Orchestration.model_validate(orch_dict), _server())
    return [ev async for ev in engine.run("go", run_id=f"run_{orch_dict['id']}", initial_state=initial_state)]


class TestRunAgentStepParams:
    async def test_orchestration_context_params(self, fake_llm):
        agent = S.make_agent(tools=["all"], skip_default_tools=True)
        fake_llm.set_default("done")
        from core.react_engine import run_agent_step
        events = [ev async for ev in run_agent_step(
            message="task", agent_id=agent["id"], session_id="s1", server_module=_server(),
            agent_override=agent, tools_override=[],
            system_prompt_extra="ORCHESTRATION AWARENESS BLOCK",
            system_prompt_prefix="ITERATION 2 BANNER",
            model_override="claude-y", source="orchestration", run_id="r1",
            allowed_tools_override=["all"], max_turns=1)]
        assert any(e.get("type") == "final" for e in events)
        # model_override took effect on the LLM call.
        assert fake_llm.last_call.get("current_model") == "claude-y"
        assert fake_llm.last_call.get("source") == "orchestration"


class TestMergeStrategies:
    @pytest.mark.parametrize("strategy", ["list", "concat", "dict"])
    async def test_merge_strategies(self, strategy):
        orch = S.make_orchestration(
            id=f"merge_{strategy}",
            entry_step_id="par",
            steps=[
                {"id": "par", "name": "Fan", "type": "parallel",
                 "parallel_branches": [["b1"], ["b2"]], "next_step_id": "mrg"},
                {"id": "b1", "name": "B1", "type": "print", "print_content": "x", "output_key": "r1", "next_step_id": None},
                {"id": "b2", "name": "B2", "type": "print", "print_content": "y", "output_key": "r2", "next_step_id": None},
                {"id": "mrg", "name": "M", "type": "merge", "merge_strategy": strategy,
                 "input_keys": ["r1", "r2"], "output_key": "m", "next_step_id": None},
            ],
        )
        events = await _run(orch)
        assert "orchestration_complete" in [e.get("type") for e in events]


class TestStepEdgeCases:
    async def test_if_else_eval_error_treated_false(self):
        orch = S.make_orchestration(
            entry_step_id="c",
            steps=[
                {"id": "c", "name": "C", "type": "if_else",
                 "if_condition": "state.missing.deep.attr == 1",  # will raise -> False
                 "if_true_step_id": "t", "if_false_step_id": "f", "next_step_id": None},
                {"id": "t", "name": "T", "type": "print", "print_content": "t", "output_key": "o", "next_step_id": None},
                {"id": "f", "name": "F", "type": "print", "print_content": "f", "output_key": "o", "next_step_id": None},
            ],
        )
        events = await _run(orch)
        decisions = [e for e in events if e.get("type") == "if_decision"]
        assert decisions and decisions[0]["result"] == "false"

    async def test_switch_with_output_key(self):
        orch = S.make_orchestration(
            entry_step_id="s",
            steps=[
                {"id": "s", "name": "S", "type": "switch", "switch_expression": "state.k",
                 "switch_cases": {"v": "a"}, "switch_default_step_id": "a",
                 "output_key": "chosen", "next_step_id": None},
                {"id": "a", "name": "A", "type": "print", "print_content": "a", "output_key": "o", "next_step_id": None},
            ],
        )
        events = await _run(orch, initial_state={"k": "v"})
        assert any(e.get("type") == "switch_decision" for e in events)

    async def test_extract_json_multiple_objects(self):
        orch = S.make_orchestration(
            entry_step_id="ex",
            steps=[{"id": "ex", "name": "Ex", "type": "extract_json",
                    "input_keys": ["blob"], "output_key": "parsed", "next_step_id": None}],
        )
        events = await _run(orch, initial_state={"blob": '{"a":1}\nand\n{"b":2}'})
        step_final = [e for e in events if e.get("type") == "final" and e.get("orch_step_id") == "ex"]
        assert step_final  # extracted a list of two objects

    async def test_print_empty_content_warns(self):
        orch = S.make_orchestration(
            entry_step_id="p",
            steps=[{"id": "p", "name": "P", "type": "print", "print_content": "   ",
                    "output_key": "o", "next_step_id": None}],
        )
        events = await _run(orch)
        assert any(e.get("type") == "step_warning" for e in events)


class TestInitialCheckpoint:
    async def test_run_file_exists_before_first_step_completes(self, tmp_path, monkeypatch):
        """The run must be visible to /runs listings from second zero — the
        checkpoint is written at run start, not first at the step boundary."""
        import json as _json
        import core.orchestration.state as state_mod
        from core.models_orchestration import Orchestration
        from core.orchestration.engine import OrchestrationEngine

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        orch = S.make_orchestration(
            id="orch_initial_ckpt",
            entry_step_id="p",
            steps=[{"id": "p", "name": "P", "type": "print", "print_content": "x",
                    "output_key": "o", "next_step_id": None}],
        )
        engine = OrchestrationEngine(Orchestration.model_validate(orch), _server())
        agen = engine.run("go", run_id="run_early")

        # Consume ONLY orchestration_start — no step has run yet.
        first = await agen.__anext__()
        assert first["type"] == "orchestration_start"
        ckpt = _json.loads((tmp_path / "runs" / "run_early.json").read_text(encoding="utf-8"))
        assert ckpt["status"] == "running"
        assert ckpt["current_step_id"] == "p"
        assert ckpt["step_history"] == []

        # Finish the run — the same file transitions to completed.
        async for _ in agen:
            pass
        ckpt = _json.loads((tmp_path / "runs" / "run_early.json").read_text(encoding="utf-8"))
        assert ckpt["status"] == "completed"


class TestRunSummaryFields:
    async def test_list_runs_exposes_live_progress(self, tmp_path, monkeypatch):
        """The runs table needs current step / progress / waiting state, not
        just status + timestamps."""
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        run = OrchestrationRun(
            run_id="run_sum", orchestration_id="o1", status="paused",
            current_step_id="s2", waiting_for_human=True, total_cost_usd=0.0125,
            step_history=[{"step_id": "s1", "step_name": "Fetch", "status": "completed"}],
        )
        state_mod.SharedState(run).checkpoint()

        [summary] = state_mod.SharedState.list_runs()
        assert summary["current_step_id"] == "s2"
        assert summary["steps_completed"] == 1
        assert summary["last_step_name"] == "Fetch"
        assert summary["waiting_for_human"] is True
        assert summary["total_cost_usd"] == 0.0125

    async def test_list_runs_limit_is_clamped(self, client, tmp_path, monkeypatch,
                                              seed_orchestration):
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        orch = seed_orchestration()  # endpoint lists only runs of live orchestrations
        for n in range(3):
            state_mod.SharedState(
                OrchestrationRun(run_id=f"run_{n}", orchestration_id=orch["id"], status="completed")
            ).checkpoint()

        assert len((await client.get("/api/orchestrations/runs?limit=2")).json()) == 2
        # Out-of-range values clamp instead of erroring.
        assert len((await client.get("/api/orchestrations/runs?limit=0")).json()) == 1
        assert len((await client.get("/api/orchestrations/runs?limit=9999")).json()) == 3

    async def test_list_runs_filters_structural_and_orphaned(self, tmp_path, monkeypatch):
        """Builder sessions and nested sub-runs are implementation details;
        runs of deleted orchestrations can't be opened. None should be listed."""
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        for run_id, orch_id in [
            ("run_real_1", "o_live"),
            ("builder_abc123", "o_live"),          # builder session
            ("run_real_1__step2_d1", "o_live"),    # nested sub-run
            ("run_orphan", "o_deleted"),           # orchestration since deleted
        ]:
            state_mod.SharedState(
                OrchestrationRun(run_id=run_id, orchestration_id=orch_id,
                                 status="completed", session_id="schedule_sched_9")
            ).checkpoint()

        listed = state_mod.SharedState.list_runs(orchestration_ids={"o_live"})
        assert [r["run_id"] for r in listed] == ["run_real_1"]
        assert listed[0]["session_id"] == "schedule_sched_9"  # trigger source

        # Without the id filter, only the structural runs are dropped.
        ids = {r["run_id"] for r in state_mod.SharedState.list_runs()}
        assert ids == {"run_real_1", "run_orphan"}

    async def test_limit_applies_after_filtering(self, tmp_path, monkeypatch):
        """A backlog of orphaned runs must not crowd live runs out of the
        limit window (they are newer by mtime here)."""
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        state_mod.SharedState(
            OrchestrationRun(run_id="run_keep", orchestration_id="o_live", status="completed")
        ).checkpoint()
        for n in range(5):  # written after → newer mtime
            state_mod.SharedState(
                OrchestrationRun(run_id=f"run_dead_{n}", orchestration_id="o_gone", status="failed")
            ).checkpoint()

        listed = state_mod.SharedState.list_runs(limit=3, orchestration_ids={"o_live"})
        assert [r["run_id"] for r in listed] == ["run_keep"]
class TestResumeVisibility:
    """A resumed run must read as 'running' on disk immediately, not only
    after its first step boundary — otherwise the active-runs list keeps
    showing it as failed/cancelled/needs-input while it is actually working."""

    def _orch(self):
        return S.make_orchestration(
            id="orch_resume_vis",
            entry_step_id="p",
            steps=[{"id": "p", "name": "P", "type": "print", "print_content": "x",
                    "output_key": "o", "next_step_id": None}],
        )

    async def test_resume_failed_marks_running_before_first_step(
        self, tmp_path, monkeypatch, seed_orchestration
    ):
        import json as _json
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun
        from core.orchestration.engine import OrchestrationEngine

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        orch = self._orch()
        seed_orchestration(**orch)
        state_mod.SharedState(OrchestrationRun(
            run_id="run_res", orchestration_id=orch["id"], status="cancelled",
            current_step_id="p",
        )).checkpoint()

        agen = OrchestrationEngine.resume_failed("run_res", _server())
        await agen.__anext__()  # first event — no step has finished yet
        ckpt = _json.loads((tmp_path / "runs" / "run_res.json").read_text(encoding="utf-8"))
        assert ckpt["status"] == "running"
        async for _ in agen:
            pass

    async def test_resume_human_clears_waiting_before_first_step(
        self, tmp_path, monkeypatch, seed_orchestration
    ):
        import json as _json
        import core.orchestration.state as state_mod
        from core.models_orchestration import OrchestrationRun
        from core.orchestration.engine import OrchestrationEngine

        monkeypatch.setattr(state_mod, "RUNS_DIR", tmp_path / "runs")
        orch = S.make_orchestration(
            id="orch_resume_human",
            entry_step_id="h",
            steps=[
                {"id": "h", "name": "Ask", "type": "human", "human_prompt": "?",
                 "output_key": "answer", "next_step_id": "p"},
                {"id": "p", "name": "P", "type": "print", "print_content": "x",
                 "output_key": "o", "next_step_id": None},
            ],
        )
        seed_orchestration(**orch)
        state_mod.SharedState(OrchestrationRun(
            run_id="run_hum", orchestration_id=orch["id"], status="paused",
            current_step_id="h", waiting_for_human=True, human_prompt="?",
        )).checkpoint()

        agen = OrchestrationEngine.resume("run_hum", {"answer": "yes"}, _server())
        await agen.__anext__()
        ckpt = _json.loads((tmp_path / "runs" / "run_hum.json").read_text(encoding="utf-8"))
        assert ckpt["status"] == "running"
        assert ckpt["waiting_for_human"] is False
        async for _ in agen:
            pass
