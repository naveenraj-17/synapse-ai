'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Save, Play, Trash, Square, Loader2, Copy, Check, Radio, Bot, Scale, GitBranch, GitMerge, RefreshCw, User, Code, Zap, Wrench, ExternalLink, X, Sparkles, Braces, GitFork, ArrowLeftRight, FileText, ArrowLeft } from 'lucide-react';
import { BuilderPanel } from '../orchestration/BuilderPanel';
import { STEP_TYPE_META } from '@/types/orchestration';
import { readWithStallTimeout } from '@/lib/sse';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowCanvas } from '../orchestration/WorkflowCanvas';
import { StepConfigPanel } from '../orchestration/StepConfigPanel';
import { StateSchemaEditor } from '../orchestration/StateSchemaEditor';
import type { Orchestration, StepConfig, StepType } from '@/types/orchestration';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ConfirmationModal } from './ConfirmationModal';
import { ToastNotification } from './ToastNotification';

type ToolCallLogEntry = { kind: 'tool_call'; tool_name: string; args: Record<string, any>; step_name?: string };
type ToolResultLogEntry = { kind: 'tool_result'; tool_name: string; preview: string };
type StepResultLogEntry = { kind: 'step_result'; step_name: string; step_type: 'agent' | 'llm' | 'print' | 'extract_json'; content: string };
// Model reasoning ([REASONING] blocks) and inter-tool prose, collapsible so a
// chatty agent doesn't drown the structural log lines.
type ReasoningLogEntry = { kind: 'reasoning'; step_name?: string; content: string };
type ThoughtLogEntry = { kind: 'thought'; step_name?: string; content: string };
type LogEntry = string | ToolCallLogEntry | ToolResultLogEntry | StepResultLogEntry | ReasoningLogEntry | ThoughtLogEntry;

type RunStepStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed';

// Pure reducer: mark each step present in a persisted checkpoint's step_history
// as completed/failed. Shared by restoreRun and reattachRun.
function applyStepHistory(
    prev: Record<string, RunStepStatus>,
    stepHistory: any[],
): Record<string, RunStepStatus> {
    const next = { ...prev };
    for (const h of stepHistory) {
        if (h?.step_id) next[h.step_id] = h.status === 'failed' ? 'failed' : 'completed';
    }
    return next;
}

const STEP_ICONS: Record<StepType, React.FC<{ size?: number }>> = {
    llm: Zap, agent: Bot, tool: Wrench, evaluator: Scale, parallel: GitBranch,
    merge: GitMerge, loop: RefreshCw, human: User, transform: Code,
    extract_json: Braces, if_else: GitFork, switch: ArrowLeftRight, print: FileText, end: Square,
};

const EMPTY_ORCHESTRATION: Orchestration = {
    id: '',
    name: 'New Orchestration',
    description: '',
    steps: [],
    entry_step_id: '',
    state_schema: {},
    max_total_turns: 100,
    max_total_cost_usd: null,
    timeout_minutes: 30,
    trigger: 'manual',
};

function generateId() {
    return 'step_' + Math.random().toString(36).substring(2, 9);
}

function newStep(type: StepType, position: { x: number; y: number }): StepConfig {
    return {
        id: generateId(),
        name: type.charAt(0).toUpperCase() + type.slice(1) + ' Step',
        type,
        position_x: position.x,
        position_y: position.y,
        max_turns: 15,
        timeout_seconds: 300,
        max_iterations: 3,
    };
}

export function OrchestrationTab({ initialRunId }: { initialRunId?: string } = {}) {
    // --- Orchestration list ---
    const [orchestrations, setOrchestrations] = useState<Orchestration[]>([]);
    const [selectedOrchId, setSelectedOrchId] = useState<string | null>(null);
    const [draft, setDraft] = useState<Orchestration | null>(null);
    const [agents, setAgents] = useState<any[]>([]);
    const [availableModels, setAvailableModels] = useState<string[]>([]);
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'warning' | 'error' } | null>(null);
    const showToast = (message: string, type: 'success' | 'warning' | 'error' = 'success') => {
        setToast({ show: true, message, type });
        setTimeout(() => setToast(null), 4000);
    };

    // --- Step selection ---
    const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

    // --- Run state ---
    const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'>('idle');
    const [runStepStatuses, setRunStepStatuses] = useState<Record<string, 'pending' | 'running' | 'paused' | 'completed' | 'failed'>>({});
    const [runId, setRunId] = useState<string | null>(null);
    const [runInput, setRunInput] = useState('');
    const [runLog, setRunLog] = useState<LogEntry[]>([]);
    const [humanPrompt, setHumanPrompt] = useState<string | null>(null);
    const [humanContext, setHumanContext] = useState<string | null>(null);
    const [humanResponse, setHumanResponse] = useState('');
    const abortRef = useRef<AbortController | null>(null);
    // Mirrors `runId` so the streamSSE catch / wake handler can read the live run
    // id without a stale closure. Timestamp of the last byte (incl. heartbeats)
    // tells a healthy stream from a dead one after sleep. reattachActiveRef
    // guards against overlapping reconnect loops.
    const currentRunIdRef = useRef<string | null>(null);
    const lastChunkAtRef = useRef(0);
    const reattachActiveRef = useRef(false);
    // Highest journal event id seen on the reattach stream (`id:` lines) — a
    // reconnect resumes with ?after=<this> instead of replaying everything.
    const lastEventIdRef = useRef(0);
    // One-line "what the model is doing right now" indicator for the Run Log.
    const [liveActivity, setLiveActivity] = useState<string | null>(null);
    // Map of orch_step_id -> pending step result (supports parallel branches)
    const pendingStepResultRef = useRef<Map<string, { step_name: string; step_type: 'agent' | 'llm' | 'print' | 'extract_json'; content: string }>>(new Map());
    const [responseModal, setResponseModal] = useState<{ step_name: string; step_type?: string; content: string } | null>(null);
    const [confirmDeleteOrchId, setConfirmDeleteOrchId] = useState<string | null>(null);
    const [builderOpen, setBuilderOpen] = useState(false);
    const [builderSessionKey, setBuilderSessionKey] = useState(0);

    // --- Active runs (for reconnect banner) ---
    type RunSummary = {
        run_id: string;
        orchestration_id: string;
        status: string;
        started_at?: string | null;
        ended_at?: string | null;
        current_step_id?: string | null;
        steps_completed?: number;
        last_step_name?: string | null;
        waiting_for_human?: boolean;
        total_cost_usd?: number | null;
        session_id?: string | null;
    };
    const [activeRuns, setActiveRuns] = useState<RunSummary[]>([]);
    const activeRunsPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const [pastRuns, setPastRuns] = useState<RunSummary[]>([]);
    // Landing dashboard: which table is shown when no orchestration is open.
    const [schedules, setSchedules] = useState<Array<{ id: string; name: string }>>([]);
    const [landingTab, setLandingTab] = useState<'orchestrations' | 'active' | 'recent' | 'all'>('orchestrations');
    const [allRuns, setAllRuns] = useState<RunSummary[]>([]);
    const autoTabRef = useRef(false);

    // --- Fetch orchestrations + agents ---
    useEffect(() => {
        fetch('/api/orchestrations').then(r => r.json()).then(data => {
            setOrchestrations(Array.isArray(data) ? data.filter((o: any) => o.id !== 'orch_native_builder') : []);
        }).catch(() => {});

        fetch('/api/agents').then(r => r.json()).then(data => {
            setAgents(Array.isArray(data) ? data : []);
        }).catch(() => {});

        fetch('/api/models').then(r => r.json()).then(data => {
            setAvailableModels(data.all_available || []);
        }).catch(() => {});

        // Schedule names, for labelling schedule-triggered runs.
        fetch('/api/schedules').then(r => r.json()).then(data => {
            setSchedules(Array.isArray(data) ? data : []);
        }).catch(() => {});
    }, []);

    // --- Poll active runs ---
    const fetchActiveRuns = useCallback(() => {
        fetch('/api/orchestrations/runs')
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) {
                    setActiveRuns(data.filter(r => r.status === 'running' || r.status === 'paused'));
                    setPastRuns(data);
                }
            })
            .catch(() => {});
    }, []);

    useEffect(() => {
        fetchActiveRuns();
        activeRunsPollRef.current = setInterval(fetchActiveRuns, 5000);
        return () => {
            if (activeRunsPollRef.current) clearInterval(activeRunsPollRef.current);
        };
    }, [fetchActiveRuns]);

    // Land on the Active table when something is running/paused (once).
    useEffect(() => {
        if (!autoTabRef.current && activeRuns.length > 0) {
            autoTabRef.current = true;
            setLandingTab('active');
        }
    }, [activeRuns]);

    // The All-runs table is heavier (up to 100 checkpoints) — fetch it only
    // while that tab is open, on a slower cadence than the active poll.
    useEffect(() => {
        if (landingTab !== 'all') return;
        const fetchAll = () => {
            fetch('/api/orchestrations/runs?limit=100')
                .then(r => r.json())
                .then(d => { if (Array.isArray(d)) setAllRuns(d); })
                .catch(() => {});
        };
        fetchAll();
        const interval = setInterval(fetchAll, 10000);
        return () => clearInterval(interval);
    }, [landingTab]);

    // --- Landing-table helpers ---
    const orchNameOf = (id: string) => orchestrations.find(o => o.id === id)?.name ?? id;
    const currentStepNameOf = (run: RunSummary): string | null => {
        const orch = orchestrations.find(o => o.id === run.orchestration_id);
        const byId = run.current_step_id
            ? orch?.steps.find(s => s.id === run.current_step_id)?.name
            : null;
        return byId || run.last_step_name || null;
    };
    // What kicked this run off. Derived from session_id, which the scheduler
    // sets to `schedule_<schedule_id>` and the orchestrator-agent path sets to
    // the chat session id; manual UI and API runs carry none.
    const triggerOf = (run: RunSummary): string => {
        const session = run.session_id || '';
        if (session.startsWith('schedule_')) {
            const schedId = session.slice('schedule_'.length);
            const sched = schedules.find(s => s.id === schedId);
            return sched ? `Schedule · ${sched.name}` : 'Schedule';
        }
        if (session) return 'Agent chat';
        return 'Manual';
    };

    const fmtDuration = (start?: string | null, end?: string | null): string => {
        if (!start) return '—';
        const s = new Date(start).getTime();
        const e = end ? new Date(end).getTime() : Date.now();
        const sec = Math.max(0, Math.round((e - s) / 1000));
        if (sec < 60) return `${sec}s`;
        const m = Math.floor(sec / 60);
        if (m < 60) return `${m}m ${sec % 60}s`;
        return `${Math.floor(m / 60)}h ${m % 60}m`;
    };
    const runStatusMeta = (run: RunSummary): { dot: string; label: string; text: string } => {
        switch (run.status) {
            case 'running': return { dot: 'bg-blue-400 animate-pulse', label: 'Running', text: 'text-blue-300' };
            case 'paused': return run.waiting_for_human
                ? { dot: 'bg-yellow-400', label: 'Needs input', text: 'text-yellow-300' }
                : { dot: 'bg-yellow-400', label: 'Paused', text: 'text-yellow-300' };
            case 'completed': return { dot: 'bg-green-500', label: 'Completed', text: 'text-zinc-400' };
            case 'cancelled': return { dot: 'bg-zinc-500', label: 'Cancelled', text: 'text-zinc-500' };
            default: return { dot: 'bg-red-500', label: 'Failed', text: 'text-red-300' };
        }
    };

    const thCls = 'px-4 py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-500 whitespace-nowrap';
    const tdCls = 'px-4 py-2.5 text-xs';

    const renderRunsTable = (rows: RunSummary[], empty: string) => (
        <div className="border border-white/5 bg-zinc-900/60">
            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-white/5 bg-zinc-950/40">
                            <th className={thCls}>Status</th>
                            <th className={thCls}>Orchestration</th>
                            <th className={thCls}>Step</th>
                            <th className={thCls}>Trigger</th>
                            <th className={`${thCls} text-right`}>Progress</th>
                            <th className={`${thCls} text-right`}>Cost</th>
                            <th className={`${thCls} text-right`}>Started</th>
                            <th className={`${thCls} text-right`}>Duration</th>
                            <th className={thCls}></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.length === 0 ? (
                            <tr>
                                <td colSpan={9} className="px-4 py-10 text-center text-xs text-zinc-600 italic">
                                    {empty}
                                </td>
                            </tr>
                        ) : rows.map(run => {
                            const meta = runStatusMeta(run);
                            const stepName = currentStepNameOf(run);
                            const isLive = run.status === 'running' || run.status === 'paused';
                            return (
                                <tr
                                    key={run.run_id}
                                    onClick={() => restoreRun(run)}
                                    className="border-b border-white/3 last:border-b-0 hover:bg-white/2 cursor-pointer transition-colors group"
                                >
                                    <td className={`${tdCls} whitespace-nowrap`}>
                                        <span className="inline-flex items-center gap-2">
                                            <span className={`w-2 h-2 rounded-full shrink-0 ${meta.dot}`} />
                                            <span className={meta.text}>{meta.label}</span>
                                        </span>
                                    </td>
                                    <td className={`${tdCls} text-zinc-200 max-w-[220px]`}>
                                        <span className="block truncate">{orchNameOf(run.orchestration_id)}</span>
                                        <span className="block text-[10px] text-zinc-600 truncate">{run.run_id}</span>
                                    </td>
                                    <td className={`${tdCls} max-w-[200px]`}>
                                        {stepName ? (
                                            <span className={`block truncate ${isLive ? 'text-zinc-300' : 'text-zinc-500'}`}>
                                                {run.status === 'running' ? '▶ ' : run.status === 'paused' ? '⏸ ' : ''}{stepName}
                                            </span>
                                        ) : <span className="text-zinc-600">—</span>}
                                    </td>
                                    <td className={`${tdCls} text-zinc-500 max-w-[160px]`}>
                                        <span className="block truncate">{triggerOf(run)}</span>
                                    </td>
                                    <td className={`${tdCls} text-right text-zinc-400 whitespace-nowrap`}>
                                        {run.steps_completed ?? 0} step{(run.steps_completed ?? 0) === 1 ? '' : 's'}
                                    </td>
                                    <td className={`${tdCls} text-right text-zinc-500 whitespace-nowrap`}>
                                        {run.total_cost_usd ? `$${run.total_cost_usd.toFixed(4)}` : '—'}
                                    </td>
                                    <td className={`${tdCls} text-right text-zinc-500 whitespace-nowrap`}>
                                        {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                                    </td>
                                    <td className={`${tdCls} text-right text-zinc-500 whitespace-nowrap`}>
                                        {fmtDuration(run.started_at, run.ended_at)}
                                    </td>
                                    <td className={`${tdCls} text-right whitespace-nowrap`}>
                                        <span className="text-[11px] text-zinc-600 group-hover:text-zinc-300 transition-colors">
                                            View →
                                        </span>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );

    // --- Restore a run from the active runs banner / recent runs / deep link ---
    // The run's event journal is replayable, so restoring = hydrate step
    // statuses from the checkpoint (fast canvas paint), then replay the journal
    // from the start — which rebuilds the exact same Run Log as live viewing —
    // and keep tailing live events until the run ends.
    const restoreRun = useCallback(async (runInfo: { run_id: string; orchestration_id: string; status: string }) => {
        const orch = orchestrations.find(o => o.id === runInfo.orchestration_id);
        if (!orch) {
            // No definition to render the canvas from — bail loudly rather than
            // setting draft to null, which would silently re-render the landing
            // page and look like the click did nothing. The runs API filters
            // these out, so this is a backstop (e.g. deleted mid-session).
            showToast('That run\'s orchestration no longer exists', 'error');
            return;
        }
        setSelectedOrchId(runInfo.orchestration_id);
        setSelectedStepId(null);
        setDraft({ ...orch });
        setRunId(runInfo.run_id);
        // Sync the ref synchronously — the useEffect that mirrors runId only runs
        // after render, but streamRunJournal's guard reads currentRunIdRef immediately.
        currentRunIdRef.current = runInfo.run_id;
        setRunStatus(runInfo.status as 'running' | 'paused' | 'completed' | 'failed' | 'cancelled');
        setHumanPrompt(null);
        setHumanContext(null);

        // Baseline: mark all steps pending (like a fresh run) before overlaying
        // completed/failed from the checkpoint.
        const seeded: Record<string, RunStepStatus> = {};
        orch.steps.forEach(s => { seeded[s.id] = 'pending'; });
        setRunStepStatuses(seeded);

        // Restore step statuses + human-input state from the persisted checkpoint
        // so the canvas is meaningful before (and in case of a pre-journal run,
        // without) the journal replay.
        try {
            const res = await fetch(`/api/orchestrations/runs/${runInfo.run_id}`);
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.step_history)) {
                    setRunStepStatuses(prev => applyStepHistory(prev, data.step_history));
                }
                if (data.waiting_for_human && data.human_prompt) {
                    setHumanPrompt(data.human_prompt);
                    setHumanContext(data.human_context || null);
                }
            }
        } catch { /* ignore */ }

        // Full-fidelity replay + live tail from the event journal. Falls back to
        // status polling for runs that predate the journal.
        const hasJournal = await streamRunJournal(runInfo.run_id, 0);
        if (!hasJournal) {
            setRunLog(['[This run predates event journaling — showing checkpoint status only.]']);
            if (runInfo.status === 'running') {
                reattachRun(runInfo.run_id, { silent: true });
            }
        }
        // streamRunJournal/reattachRun are stable useCallback([])s declared below;
        // adding them to the deps array would be a temporal-dead-zone read during render.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [orchestrations]);

    // --- Select orchestration ---
    const selectOrchestration = useCallback((id: string | null) => {
        setSelectedOrchId(id);
        setSelectedStepId(null);
        setRunStatus('idle');
        setRunStepStatuses({});
        setRunLog([]);
        setHumanPrompt(null);
        if (id) {
            const orch = orchestrations.find(o => o.id === id);
            setDraft(orch ? { ...orch } : null);
        } else {
            setDraft(null);
        }
    }, [orchestrations]);

    // --- Back to the landing dashboard ---
    // Detaches this browser from the run's event stream; the run itself keeps
    // executing server-side on the runner pump and stays listed under Active,
    // so leaving the view never interrupts work.
    const backToList = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = null;
        currentRunIdRef.current = null;  // stops streamRunJournal's tail loop
        setRunId(null);
        setLiveActivity(null);
        selectOrchestration(null);
    }, [selectOrchestration]);

    // --- Create new orchestration ---
    const createNew = () => {
        const id = 'orch_' + Math.random().toString(36).substring(2, 9);
        const orch: Orchestration = { ...EMPTY_ORCHESTRATION, id };
        setDraft(orch);
        setSelectedOrchId(id);
        setSelectedStepId(null);
    };

    // --- Duplicate orchestration ---
    const handleDuplicate = async () => {
        if (!draft) return;

        // Build old→new step ID map
        const idMap: Record<string, string> = {};
        for (const step of draft.steps) {
            idMap[step.id] = generateId();
        }

        // Remap a step ID reference, preserving null/undefined
        const remap = (id: string | null | undefined): string | null | undefined => {
            if (id == null) return id;
            return idMap[id] ?? id;
        };

        // Clone steps with remapped IDs
        const clonedSteps: StepConfig[] = draft.steps.map(step => ({
            ...step,
            id: idMap[step.id],
            next_step_id: remap(step.next_step_id) as string | undefined,
            route_map: step.route_map
                ? Object.fromEntries(
                    Object.entries(step.route_map).map(([label, target]) => [
                        label,
                        target != null ? (idMap[target as string] ?? target) : null,
                    ])
                  )
                : undefined,
            parallel_branches: step.parallel_branches?.map(branch =>
                branch.map(sid => idMap[sid] ?? sid)
            ),
            loop_step_ids: step.loop_step_ids?.map(sid => idMap[sid] ?? sid),
            // IF_ELSE remapping
            if_true_step_id: remap(step.if_true_step_id) as string | undefined,
            if_false_step_id: remap(step.if_false_step_id) as string | undefined,
            // SWITCH remapping
            switch_cases: step.switch_cases
                ? Object.fromEntries(
                    Object.entries(step.switch_cases).map(([val, target]) => [
                        val,
                        target != null ? (idMap[target as string] ?? target) : null,
                    ])
                  )
                : undefined,
            switch_default_step_id: remap(step.switch_default_step_id) as string | undefined,
        }));

        const newId = 'orch_' + Math.random().toString(36).substring(2, 9);
        const clone: Orchestration = {
            ...draft,
            id: newId,
            name: draft.name + ' (Copy)',
            steps: clonedSteps,
            entry_step_id: draft.entry_step_id ? (idMap[draft.entry_step_id] ?? '') : '',
            state_schema: JSON.parse(JSON.stringify(draft.state_schema ?? {})),
            created_at: undefined,
            updated_at: undefined,
        };

        setSaving(true);
        try {
            const res = await fetch('/api/orchestrations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(clone),
            });
            if (res.ok) {
                const saved = await res.json();
                setOrchestrations(prev => [...prev, saved]);
                setDraft(saved);
                setSelectedOrchId(newId);
                setSelectedStepId(null);
            }
        } catch { /* ignore */ } finally {
            setSaving(false);
        }
    };

    // --- Save orchestration ---
    const handleSave = async () => {
        if (!draft) return;
        setSaving(true);
        try {
            const res = await fetch('/api/orchestrations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(draft),
            });
            if (res.ok) {
                const saved = await res.json();
                const idx = orchestrations.findIndex(o => o.id === saved.id);
                if (idx >= 0) {
                    const next = [...orchestrations];
                    next[idx] = saved;
                    setOrchestrations(next);
                } else {
                    setOrchestrations([...orchestrations, saved]);
                }
                setDraft(saved);
            }
        } catch { /* ignore */ } finally {
            setSaving(false);
        }
    };

    // --- Delete orchestration ---
    const handleDelete = () => {
        if (!draft) return;
        setConfirmDeleteOrchId(draft.id);
    };

    const confirmDeleteOrchestration = async () => {
        if (!confirmDeleteOrchId) return;
        try {
            await fetch(`/api/orchestrations/${confirmDeleteOrchId}`, { method: 'DELETE' });
            setOrchestrations(orchestrations.filter(o => o.id !== confirmDeleteOrchId));
            if (draft?.id === confirmDeleteOrchId) {
                setDraft(null);
                setSelectedOrchId(null);
            }
        } catch { /* ignore */ }
    };

    // --- Add step ---
    const addStep = (type: StepType) => {
        if (!draft) return;
        const existingCount = draft.steps.length;
        const step = newStep(type, { x: 100 + (existingCount % 3) * 250, y: 80 + Math.floor(existingCount / 3) * 180 });
        const updated = { ...draft, steps: [...draft.steps, step] };
        if (!updated.entry_step_id) {
            updated.entry_step_id = step.id;
        }
        setDraft(updated);
    };

    // --- Update step ---
    const updateStep = useCallback((updatedStep: StepConfig) => {
        if (!draft) return;
        setDraft({
            ...draft,
            steps: draft.steps.map(s => s.id === updatedStep.id ? updatedStep : s),
        });
    }, [draft]);

    // --- Delete step ---
    const deleteStep = useCallback((stepId: string) => {
        if (!draft) return;
        const updated = {
            ...draft,
            steps: draft.steps.filter(s => s.id !== stepId),
        };
        // Clean references
        updated.steps = updated.steps.map(s => {
            const patched: any = {
                ...s,
                next_step_id: s.next_step_id === stepId ? undefined : s.next_step_id,
                loop_step_ids: s.loop_step_ids?.filter(id => id !== stepId),
                parallel_branches: s.parallel_branches?.map(branch => branch.filter(id => id !== stepId)),
                // Clean if_else references
                if_true_step_id: s.if_true_step_id === stepId ? undefined : s.if_true_step_id,
                if_false_step_id: s.if_false_step_id === stepId ? undefined : s.if_false_step_id,
                // Clean switch default
                switch_default_step_id: s.switch_default_step_id === stepId ? undefined : s.switch_default_step_id,
            };
            // Clean route_map entries pointing to deleted step
            if (s.route_map) {
                const newRouteMap: Record<string, string | null> = {};
                for (const [label, target] of Object.entries(s.route_map)) {
                    newRouteMap[label] = target === stepId ? null : target;
                }
                patched.route_map = newRouteMap;
            }
            // Clean switch_cases entries pointing to deleted step
            if (s.switch_cases) {
                const newCases: Record<string, string | null> = {};
                for (const [val, target] of Object.entries(s.switch_cases)) {
                    newCases[val] = target === stepId ? null : target;
                }
                patched.switch_cases = newCases;
            }
            return patched;
        });
        if (updated.entry_step_id === stepId) {
            updated.entry_step_id = updated.steps[0]?.id || '';
        }
        setDraft(updated);
        if (selectedStepId === stepId) setSelectedStepId(null);
    }, [draft, selectedStepId]);

    // --- Set entry point ---
    const setEntryPoint = useCallback((stepId: string) => {
        if (!draft) return;
        setDraft({ ...draft, entry_step_id: stepId });
    }, [draft]);

    // --- Update orchestration from canvas (position changes, edge connections) ---
    const updateOrchestration = useCallback((orch: Orchestration) => {
        setDraft(orch);
    }, []);

    // --- Reattach stream: replay the run's event journal, then tail it live ---
    // The engine runs in a background task on the server and keeps executing
    // even if this client disconnects (e.g. the laptop slept), journaling every
    // event. Reattaching = GET the journal SSE stream: full replay from
    // `after`, then live tail until the run truly ends. Reconnects resume from
    // the last seen event id. Returns false iff the run has no journal
    // (predates the feature) so callers can fall back to status polling.
    const streamRunJournal = useCallback(async (rid: string, after: number): Promise<boolean> => {
        lastEventIdRef.current = after;
        let attempts = 0;
        while (true) {
            if (currentRunIdRef.current !== rid) return true;  // user switched runs
            const controller = new AbortController();
            abortRef.current?.abort();                          // never two feeds at once
            abortRef.current = controller;
            lastChunkAtRef.current = Date.now();
            try {
                const res = await fetch(
                    `/api/orchestrations/runs/${rid}/events/stream?after=${lastEventIdRef.current}`,
                    { signal: controller.signal },
                );
                if (res.status === 404) return false;           // pre-journal run
                if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
                if (lastEventIdRef.current === 0) {
                    // Full replay rebuilds the log from scratch — identical to
                    // having watched the run live, with no duplicated entries.
                    setRunLog([]);
                }
                attempts = 0;
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                while (true) {
                    const { done, value } = await readWithStallTimeout(reader, controller);
                    if (done) break;
                    lastChunkAtRef.current = Date.now();
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    // Events in one chunk are processed synchronously — React
                    // batches the state updates, so a multi-hundred-event replay
                    // costs a handful of renders instead of one per event.
                    for (const line of lines) {
                        if (line.startsWith('id: ')) {
                            const id = parseInt(line.slice(4), 10);
                            if (!Number.isNaN(id)) lastEventIdRef.current = id;
                        } else if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'stream_complete') return true;  // run truly over
                                handleSSEEvent(data, true);
                            } catch { /* ignore parse errors */ }
                        }
                    }
                }
                // Stream ended without stream_complete (proxy drop, server
                // restart) — reconnect from where we left off.
                throw new Error('stream ended early');
            } catch (e: any) {
                // A terminal event handler or run switch aborts us on purpose;
                // 'recover' (wake handler) and transport errors mean reconnect.
                const intentional = e?.name === 'AbortError' && controller.signal.reason !== 'recover';
                if (intentional) return true;
                if (++attempts > 20) {
                    setRunLog(prev => [...prev, '[Reconnect failed — see Active Runs to rejoin]']);
                    return true;
                }
                await new Promise<void>(r => setTimeout(r, Math.min(3000, 500 * attempts)));
            } finally {
                if (abortRef.current === controller) abortRef.current = null;
            }
        }
    }, []);

    // --- Re-attach to a run after the SSE connection drops ---
    // Journal replay is the primary path; polling remains only for runs that
    // predate event journaling.
    const reattachRun = useCallback(async (rid: string | null, opts?: { silent?: boolean }) => {
        if (!rid) { setRunStatus('failed'); setRunLog(prev => [...prev, '[Connection lost]']); return; }
        if (reattachActiveRef.current) return;       // already reconnecting
        reattachActiveRef.current = true;
        try {
            const hasJournal = await streamRunJournal(rid, 0);
            if (!hasJournal) await pollRunStatus(rid, opts);
        } finally {
            reattachActiveRef.current = false;
        }
        // streamRunJournal/pollRunStatus are stable useCallback([])s.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Legacy fallback: track a pre-journal run to completion by polling its
    // step-boundary checkpoint.
    const pollRunStatus = useCallback(async (rid: string, opts?: { silent?: boolean }) => {
        if (!opts?.silent) setRunLog(prev => [...prev, '[Connection lost — reconnecting to run…]']);
        const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));
        const deadline = Date.now() + 10 * 60 * 1000; // give up after 10 min
        let notFound = 0; // tolerate brief 404 windows at run start/end before giving up
        {
            while (Date.now() < deadline) {
                if (currentRunIdRef.current !== rid) return;  // user started/restored a different run
                let data: any;
                try {
                    const res = await fetch(`/api/orchestrations/runs/${rid}`);
                    if (res.status === 404) {
                        if (++notFound >= 3) {
                            setRunStatus('failed');
                            setRunLog(prev => [...prev, '[Reconnect failed — run not found]']);
                            return;
                        }
                        await sleep(3000); continue;
                    }
                    if (!res.ok) { await sleep(3000); continue; }
                    notFound = 0;
                    data = await res.json();
                } catch { await sleep(3000); continue; }

                // Sync step statuses from the persisted history
                if (Array.isArray(data.step_history)) {
                    setRunStepStatuses(prev => applyStepHistory(prev, data.step_history));
                }

                if (data.status === 'running') {
                    setRunStatus('running');
                    await sleep(3000);
                    continue;
                }
                if (data.status === 'paused') {
                    setRunStatus('paused');
                    if (data.waiting_for_human && data.human_prompt) {
                        setHumanPrompt(data.human_prompt);
                        setHumanContext(data.human_context || null);
                    }
                    setRunLog(prev => [...prev, '[Reconnected — run is waiting for your input]']);
                    return;
                }
                // Terminal: completed / failed / cancelled
                const final = data.status === 'completed' ? 'completed' : data.status === 'cancelled' ? 'cancelled' : 'failed';
                setRunStatus(final);
                setHumanPrompt(null);
                setHumanContext(null);
                setRunLog(prev => [...prev, `[Reconnected — run ${data.status}]`]);
                return;
            }
            setRunLog(prev => [...prev, '[Reconnect timed out — see Active Runs to rejoin]']);
        }
    }, []);

    // --- SSE stream reader helper (POST run/resume/human-input streams) ---
    const streamSSE = async (url: string, body: Record<string, any>) => {
        const controller = new AbortController();
        abortRef.current?.abort();  // e.g. close a reattach tail before resuming
        abortRef.current = controller;
        lastChunkAtRef.current = Date.now();

        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: controller.signal,
            });
            if (!res.ok || !res.body) {
                setRunStatus('failed');
                setRunLog(prev => [...prev, `[HTTP ${res.status}]`]);
                return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await readWithStallTimeout(reader, controller);
                if (done) break;
                lastChunkAtRef.current = Date.now();  // heartbeats keep this fresh while alive
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            handleSSEEvent(data);
                            // Yield to the macrotask queue so React flushes
                            // state updates between events rather than batching
                            // them all into a single render at stream end.
                            await new Promise<void>(resolve => setTimeout(resolve, 0));
                        } catch { /* ignore parse errors */ }
                    }
                }
            }
        } catch (e: any) {
            // A stall/transport error, or a 'recover' abort from the wake handler,
            // means the connection dropped while the run is likely still executing
            // server-side → re-attach via polling. A plain AbortError is an
            // intentional stop (cancel / unmount / terminal event) → ignore.
            const lostConnection = e.name !== 'AbortError' || controller.signal.reason === 'recover';
            if (lostConnection) {
                reattachRun(currentRunIdRef.current);
            }
        } finally {
            abortRef.current = null;
        }
    };

    // --- Run orchestration ---
    const startRun = () => {
        if (!draft) return;
        const statuses: Record<string, 'pending' | 'running' | 'completed' | 'failed'> = {};
        draft.steps.forEach(s => { statuses[s.id] = 'pending'; });
        setRunStepStatuses(statuses);
        setRunStatus('running');
        setRunLog([]);
        setHumanPrompt(null);
        setLiveActivity(null);
        lastEventIdRef.current = 0;  // fresh run, fresh journal

        streamSSE(`/api/orchestrations/${draft.id}/run`, { message: runInput });
    };

    // `fromJournal` marks events arriving from the replay/tail stream. A
    // journal can contain a terminal event mid-file (cancel, then resume
    // appends more events to the same run), so terminal handlers must NOT
    // abort the feed there — the server signals the real end with
    // `stream_complete`. Aborting on the live POST stream stays correct.
    const handleSSEEvent = (data: any, fromJournal = false) => {
        switch (data.type) {
            case 'orchestration_start':
                setRunId(data.run_id);
                setRunLog(prev => [...prev, `Started run ${data.run_id}`]);
                break;

            case 'step_start': {
                // Progress after a pause means the pending input was consumed
                // (submitted here, in another tab, or via messaging) — drop the
                // stale form. Matters for journal replay of resumed runs too.
                setHumanPrompt(null);
                setHumanContext(null);
                setRunStatus('running');
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'running' }));
                setRunLog(prev => [...prev, `▶ ${data.step_name} (${data.step_type})`]);
                // Begin tracking response for agent/llm/print/extract_json steps, keyed by step id
                if (data.step_type === 'agent' || data.step_type === 'llm' || data.step_type === 'print' || data.step_type === 'extract_json') {
                    pendingStepResultRef.current.set(data.orch_step_id, {
                        step_name: data.step_name,
                        step_type: data.step_type as 'agent' | 'llm' | 'print' | 'extract_json',
                        content: '',
                    });
                } else {
                    pendingStepResultRef.current.delete(data.orch_step_id);
                }
                break;
            }

            case 'step_complete': {
                setLiveActivity(null);
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'completed' }));
                const pendingForStep = pendingStepResultRef.current.get(data.orch_step_id);
                setRunLog(prev => {
                    const next = [...prev, `✓ ${data.step_name} completed (${data.duration_seconds?.toFixed(1)}s)`];
                    if (pendingForStep && pendingForStep.content.trim()) {
                        next.splice(next.length - 1, 0, {
                            kind: 'step_result',
                            step_name: pendingForStep.step_name,
                            step_type: pendingForStep.step_type,
                            content: pendingForStep.content.trim(),
                        } as StepResultLogEntry);
                    }
                    return next;
                });
                pendingStepResultRef.current.delete(data.orch_step_id);
                break;
            }

            case 'step_error':
                setLiveActivity(null);
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'failed' }));
                setRunLog(prev => [...prev, `✗ Step error: ${data.error}`]);
                pendingStepResultRef.current.delete(data.orch_step_id);
                break;

            case 'llm_reasoning':
                if (data.reasoning) {
                    setLiveActivity(`🧠 ${String(data.reasoning).split('\n')[0].slice(0, 140)}`);
                    setRunLog(prev => [...prev, {
                        kind: 'reasoning',
                        step_name: data.step_name,
                        content: String(data.reasoning),
                    } as ReasoningLogEntry]);
                }
                break;

            case 'llm_thought':
                if (data.thought) {
                    setRunLog(prev => [...prev, {
                        kind: 'thought',
                        step_name: data.step_name,
                        content: String(data.thought),
                    } as ThoughtLogEntry]);
                }
                break;

            case 'thinking':
                // Chatty progress line ("Analyzing...", "Delegating to X...") —
                // shown as the live activity indicator, not appended to the log.
                if (data.message) setLiveActivity(`💭 ${data.message}`);
                break;

            case 'status':
                if (data.message) setRunLog(prev => [...prev, `ℹ ${data.message}`]);
                break;

            case 'step_warning':
                setRunLog(prev => [...prev, `⚠ ${data.message || 'Step warning'}`]);
                break;

            case 'context_compact':
                setRunLog(prev => [...prev,
                    `⇲ Context compacted (${data.chars_before ?? '?'} → ${data.chars_after ?? '?'} chars)`]);
                break;

            case 'final': {
                // Capture the full final response keyed by step id
                const response = data.response || '';
                const stepId = data.orch_step_id || '';
                if (stepId && pendingStepResultRef.current.has(stepId) && response) {
                    pendingStepResultRef.current.get(stepId)!.content = response;
                }
                break;
            }

            case 'routing_decision':
                setRunLog(prev => [...prev, `🔀 Evaluator routed → ${data.decision} (${data.reasoning || ''})`]);
                break;

            case 'if_decision':
                setRunLog(prev => [...prev, `🔀 If/Else: ${data.condition || ''} → ${data.result}`]);
                break;

            case 'switch_decision':
                setRunLog(prev => [...prev, `🔀 Switch: ${data.expression || ''} = "${data.value}" → ${data.matched_case ?? 'default'}`]);
                break;

            case 'parallel_start':
                setRunLog(prev => [...prev, `⫘ Parallel: running ${data.branch_count} branches`]);
                break;

            case 'branch_start':
                setRunLog(prev => [...prev, `  ↳ Branch ${(data.branch_index ?? 0) + 1}/${data.branch_count}`]);
                break;

            case 'parallel_complete':
                setRunLog(prev => [...prev, `⫘ Parallel: all ${data.branch_count} branches done`]);
                break;

            case 'loop_iteration':
                setRunLog(prev => [...prev, `⟳ Loop iteration ${data.iteration}/${data.total}`]);
                break;

            case 'merge_complete':
                setRunLog(prev => [...prev, `⊕ Merged ${data.input_count} inputs (${data.strategy})`]);
                break;

            case 'orchestration_end':
                setRunLog(prev => [...prev, `■ End node reached`]);
                break;

            case 'human_input_required':
                setLiveActivity(null);
                setRunStatus('paused');
                if (data.orch_step_id) setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'paused' }));
                setHumanPrompt(data.prompt || 'Please provide input:');
                setHumanContext(data.agent_context || null);
                setRunLog(prev => [...prev, `⏸ Waiting for human input...`]);
                break;

            case 'loop_limit_reached':
                setRunLog(prev => [...prev, `⟳ Loop limit reached for step ${data.orch_step_id} (${data.iterations} iterations)`]);
                break;

            case 'orchestration_complete':
                setLiveActivity(null);
                setHumanPrompt(null);
                setHumanContext(null);
                setRunStatus(data.status === 'completed' ? 'completed' : 'failed');
                setRunLog(prev => [...prev, `Done — status: ${data.status}`]);
                if (!fromJournal) {
                    abortRef.current?.abort();
                    abortRef.current = null;
                }
                break;

            case 'orchestration_error':
                setLiveActivity(null);
                setHumanPrompt(null);
                setHumanContext(null);
                setRunStatus('failed');
                setRunLog(prev => [...prev, `Error: ${data.error}`]);
                if (!fromJournal) {
                    abortRef.current?.abort();
                    abortRef.current = null;
                }
                break;

            case 'tool_execution':
                setLiveActivity(`🔧 ${data.tool_name}`);
                setRunLog(prev => [...prev, {
                    kind: 'tool_call',
                    tool_name: data.tool_name,
                    args: data.args || {},
                    step_name: data.step_name,
                } as ToolCallLogEntry]);
                break;

            case 'tool_result':
                setRunLog(prev => [...prev, {
                    kind: 'tool_result',
                    tool_name: data.tool_name,
                    preview: data.preview || '',
                } as ToolResultLogEntry]);
                break;

            case 'token_usage':
                // Silently track
                break;

            default:
                // chunk events are accumulated in pendingStepResultRef (via 'final'),
                // so we only show a live streaming indicator if there's no pending capture
                if (data.type === 'chunk' && data.content && !pendingStepResultRef.current) {
                    setRunLog(prev => {
                        const last = prev[prev.length - 1];
                        if (last && typeof last === 'string' && last.startsWith('  ')) {
                            return [...prev.slice(0, -1), last + data.content];
                        }
                        return [...prev, '  ' + data.content];
                    });
                }
                break;
        }
    };

    const cancelRun = async () => {
        setLiveActivity(null);
        abortRef.current?.abort();
        abortRef.current = null;
        if (runId) {
            try {
                await fetch(`/api/orchestrations/runs/${runId}/cancel`, { method: 'POST' });
            } catch { /* ignore */ }
        }
        setRunStatus('cancelled');
        setRunLog(prev => [...prev, '[Cancelled]']);
    };

    const submitHumanInput = async () => {
        if (!runId) return;
        setHumanPrompt(null);
        setHumanContext(null);
        setRunStatus('running');
        setRunStepStatuses(prev => {
            const next = { ...prev };
            for (const k in next) { if (next[k] === 'paused') next[k] = 'running'; }
            return next;
        });
        setRunLog(prev => [...prev, `Human response submitted`]);
        const response = humanResponse;
        setHumanResponse('');

        streamSSE(`/api/orchestrations/runs/${runId}/human-input`, { response });
    };

    const resumeRun = async () => {
        if (!runId) return;
        setRunStatus('running');
        setRunLog(prev => [...prev, '[Resuming from where run stopped...]']);
        streamSSE(`/api/orchestrations/runs/${runId}/resume`, {});
    };

    // Keep a ref mirror of runId so async handlers read the live value.
    useEffect(() => { currentRunIdRef.current = runId; }, [runId]);

    // Deep link (?run=<run_id>): once orchestrations are loaded, open that run
    // exactly as if it was clicked in the Active Runs banner.
    const initialRunConsumedRef = useRef(false);
    useEffect(() => {
        if (!initialRunId || initialRunConsumedRef.current || orchestrations.length === 0) return;
        initialRunConsumedRef.current = true;
        (async () => {
            try {
                const res = await fetch(`/api/orchestrations/runs/${initialRunId}`);
                if (!res.ok) return;
                const data = await res.json();
                restoreRun({
                    run_id: initialRunId,
                    orchestration_id: data.orchestration_id || '',
                    status: data.status || 'running',
                });
            } catch { /* ignore */ }
        })();
        // restoreRun is recreated when orchestrations load; the consumed ref
        // keeps this one-shot.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialRunId, orchestrations]);

    // Wake / network recovery: on refocus or network-back, if a run's stream has
    // gone silent past several heartbeat windows (≈ dead socket after sleep),
    // abort it with a 'recover' reason so streamSSE re-attaches to the run.
    // A recent chunk (heartbeat <60s ago) means it's alive — leave it be.
    useEffect(() => {
        const maybeRecover = () => {
            if (!abortRef.current) return;                         // no active stream
            if (document.visibilityState === 'hidden') return;
            if (Date.now() - lastChunkAtRef.current <= 60000) return;
            abortRef.current.abort('recover');
        };
        window.addEventListener('online', maybeRecover);
        document.addEventListener('visibilitychange', maybeRecover);
        return () => {
            window.removeEventListener('online', maybeRecover);
            document.removeEventListener('visibilitychange', maybeRecover);
        };
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            abortRef.current?.abort();
        };
    }, []);

    const selectedStep = draft?.steps.find(s => s.id === selectedStepId) || null;
    const allStepIds = draft?.steps.map(s => ({ id: s.id, name: s.name })) || [];

    // --- Deploy as agent ---
    const handleDeploy = async () => {
        if (!draft) return;
        try {
            const res = await fetch(`/api/orchestrations/${draft.id}/deploy`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                showToast(`Deployed as agent "${draft.name}" (${data.agent_id})`, 'success');
            } else {
                const err = await res.json();
                showToast(`Deploy failed: ${err.detail || 'Unknown error'}`, 'error');
            }
        } catch {
            showToast('Failed to deploy orchestration as agent', 'error');
        }
    };

    return (
        <div className="flex flex-col h-full relative">
            {toast && <ToastNotification show={toast.show} message={toast.message} type={toast.type} />}
            {/* Header */}
            <div className="px-6 py-4 border-b border-zinc-800 shrink-0">
                <h1 className="text-2xl font-bold text-zinc-100">Orchestrations</h1>
                <p className="text-zinc-500 text-xs mt-0.5">Design multi-agent workflows with visual canvas</p>
            </div>

            {/* Toolbar: orchestration picker + actions */}
            <div className="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800 shrink-0">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    {draft && (
                        <button
                            onClick={backToList}
                            title="Back to all orchestrations and runs"
                            className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-white border border-zinc-700 hover:border-white transition-colors shrink-0"
                        >
                            <ArrowLeft size={14} /> Back
                        </button>
                    )}
                    <select
                        className="bg-zinc-900 border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 outline-none max-w-[240px]"
                        value={selectedOrchId || ''}
                        onChange={(e) => selectOrchestration(e.target.value || null)}
                    >
                        <option value="">Select orchestration...</option>
                        {orchestrations.map(o => (
                            <option key={o.id} value={o.id}>{o.name}</option>
                        ))}
                    </select>
                    <button
                        onClick={createNew}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white transition-colors"
                    >
                        <Plus size={14} /> New
                    </button>
                    <button
                        onClick={() => { 
                            if (!selectedOrchId) createNew(); 
                            setBuilderOpen(true); 
                            setBuilderSessionKey(k => k + 1); 
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 text-white transition-colors"
                    >
                        <Sparkles size={13} /> Build with AI
                    </button>
                </div>

                {draft && (
                    <div className="flex items-center gap-2 pr-6">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 transition-colors disabled:opacity-50"
                        >
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
                        </button>
                        {runStatus === 'idle' || runStatus === 'completed' || runStatus === 'failed' || runStatus === 'cancelled' ? (
                            <button
                                onClick={startRun}
                                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-600 hover:bg-green-500 text-white transition-colors"
                            >
                                <Play size={14} /> Run
                            </button>
                        ) : (
                            <button
                                onClick={cancelRun}
                                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red-600 hover:bg-red-500 text-white transition-colors"
                            >
                                <Square size={14} /> Cancel
                            </button>
                        )}
                        <button
                            onClick={handleDeploy}
                            className="px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 text-white transition-colors"
                        >
                            Deploy as Agent
                        </button>
                        <button
                            onClick={handleDuplicate}
                            disabled={saving}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 transition-colors disabled:opacity-50"
                        >
                            <Copy size={13} /> Duplicate
                        </button>
                        <div className="w-px h-5 bg-zinc-700 mx-1" />
                        <button
                            onClick={handleDelete}
                            className="flex items-center gap-1 px-2 py-1.5 text-xs text-zinc-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                        >
                            <Trash size={13} /> Delete
                        </button>
                    </div>
                )}
            </div>

            {/* Active runs banner */}
            {activeRuns.filter(r => r.run_id !== runId).length > 0 && (
                <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-900/60 shrink-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-zinc-500 flex items-center gap-1">
                            <Radio size={11} className="text-blue-400 animate-pulse" /> Active runs:
                        </span>
                        {activeRuns.filter(r => r.run_id !== runId).map(run => {
                            const orch = orchestrations.find(o => o.id === run.orchestration_id);
                            return (
                                <button
                                    key={run.run_id}
                                    onClick={() => restoreRun(run)}
                                    className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
                                >
                                    <span className={`w-1.5 h-1.5 rounded-full ${
                                        run.status === 'running' ? 'bg-blue-400 animate-pulse' : 'bg-yellow-400'
                                    }`} />
                                    <span className="text-zinc-300">{orch?.name ?? run.orchestration_id}</span>
                                    <span className="text-zinc-500">{run.status === 'paused' ? '· waiting for input' : '· running'}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            )}

            {!draft ? (
                /* ── Landing dashboard: tabbed tables ────────────────────── */
                <div className="flex-1 overflow-y-auto modern-scrollbar">
                    <div className="px-4 pb-8">
                        {/* Tab bar */}
                        <div className="flex items-end border-b border-white/5 mb-4">
                            <div className="flex items-center">
                                {([
                                    { id: 'orchestrations', label: 'Orchestrations', count: orchestrations.length },
                                    { id: 'active', label: 'Active', count: activeRuns.length },
                                    { id: 'recent', label: 'Recent', count: null },
                                    { id: 'all', label: 'All runs', count: null },
                                ] as const).map(t => (
                                    <button
                                        key={t.id}
                                        onClick={() => setLandingTab(t.id)}
                                        className={`px-4 py-2.5 text-xs font-medium border-b -mb-px transition-colors ${
                                            landingTab === t.id
                                                ? 'text-zinc-100 border-zinc-100'
                                                : 'text-zinc-500 border-transparent hover:text-zinc-300'
                                        }`}
                                    >
                                        {t.label}
                                        {t.count !== null && t.count > 0 && (
                                            <span className={`ml-1.5 px-1.5 py-0.5 text-[10px] ${
                                                t.id === 'active'
                                                    ? 'bg-blue-500/20 text-blue-300'
                                                    : 'bg-white/5 text-zinc-400'
                                            }`}>{t.count}</span>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {landingTab === 'orchestrations' && (
                            <div className="border border-white/5 bg-zinc-900/60">
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-white/5 bg-zinc-950/40">
                                                <th className={thCls}>Name</th>
                                                <th className={thCls}>Description</th>
                                                <th className={`${thCls} text-right`}>Steps</th>
                                                <th className={`${thCls} text-right`}>Last run</th>
                                                <th className={thCls}></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {orchestrations.length === 0 ? (
                                                <tr>
                                                    <td colSpan={5} className="px-4 py-10 text-center text-xs text-zinc-600 italic">
                                                        No orchestrations yet — create one or build with AI.
                                                    </td>
                                                </tr>
                                            ) : orchestrations.map(o => {
                                                const lastRun = pastRuns.find(r => r.orchestration_id === o.id);
                                                const lastMeta = lastRun ? runStatusMeta(lastRun) : null;
                                                return (
                                                    <tr
                                                        key={o.id}
                                                        onClick={() => selectOrchestration(o.id)}
                                                        className="border-b border-white/3 last:border-b-0 hover:bg-white/2 cursor-pointer transition-colors group"
                                                    >
                                                        <td className={`${tdCls} text-zinc-200 font-medium whitespace-nowrap max-w-[240px]`}>
                                                            <span className="block truncate">{o.name}</span>
                                                        </td>
                                                        <td className={`${tdCls} text-zinc-500 max-w-[380px]`}>
                                                            <span className="block truncate">{o.description || '—'}</span>
                                                        </td>
                                                        <td className={`${tdCls} text-right text-zinc-400 whitespace-nowrap`}>
                                                            {o.steps.length}
                                                        </td>
                                                        <td className={`${tdCls} text-right whitespace-nowrap`}>
                                                            {lastRun && lastMeta ? (
                                                                <span className="inline-flex items-center gap-1.5 justify-end">
                                                                    <span className={`w-1.5 h-1.5 rounded-full ${lastMeta.dot}`} />
                                                                    <span className="text-zinc-500">
                                                                        {lastRun.started_at ? new Date(lastRun.started_at).toLocaleString() : lastMeta.label}
                                                                    </span>
                                                                </span>
                                                            ) : <span className="text-zinc-600">never</span>}
                                                        </td>
                                                        <td className={`${tdCls} text-right whitespace-nowrap`}>
                                                            <span className="text-[11px] text-zinc-600 group-hover:text-zinc-300 transition-colors">
                                                                Open →
                                                            </span>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {landingTab === 'active' && renderRunsTable(
                            activeRuns,
                            'No active runs — start one from the Orchestrations tab.',
                        )}

                        {landingTab === 'recent' && renderRunsTable(
                            pastRuns.filter(r => r.status !== 'running' && r.status !== 'paused').slice(0, 10),
                            'No finished runs yet.',
                        )}

                        {landingTab === 'all' && renderRunsTable(
                            allRuns.length > 0 ? allRuns : pastRuns,
                            'No runs recorded yet.',
                        )}
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex flex-col min-h-0">
                    {/* Name + description */}
                    <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0">
                        <input
                            className="bg-transparent border-b border-zinc-700 text-zinc-200 text-sm font-medium px-1 py-0.5 outline-none focus:border-blue-500 w-64"
                            value={draft.name}
                            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                            placeholder="Orchestration name"
                        />
                        <input
                            className="bg-transparent border-b border-zinc-700 text-zinc-400 text-xs px-1 py-0.5 outline-none focus:border-blue-500 flex-1 mr-6"
                            value={draft.description}
                            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                            placeholder="Description..."
                        />
                    </div>

                    {/* Step type toolbar */}
                    <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800 shrink-0">
                        <span className="text-xs text-zinc-500 mr-2">Add step:</span>
                        {(['llm', 'agent', 'tool', 'evaluator', 'parallel', 'merge', 'loop', 'human', 'transform', 'extract_json', 'if_else', 'switch', 'print', 'end'] as StepType[]).map(type => {
                            const meta = STEP_TYPE_META[type];
                            const Icon = STEP_ICONS[type];
                            return (
                                <button
                                    key={type}
                                    onClick={() => addStep(type)}
                                    className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors capitalize"
                                >
                                    <Icon size={12} />
                                    {meta.label}
                                </button>
                            );
                        })}
                    </div>

                    {/* Main content: canvas + optional side panel */}
                    <div className="flex-1 flex min-h-0">
                        {/* Canvas */}
                        <div className="flex-1 min-w-0">
                            <ReactFlowProvider>
                                <WorkflowCanvas
                                    orchestration={draft}
                                    agents={agents}
                                    selectedStepId={selectedStepId}
                                    onSelectStep={setSelectedStepId}
                                    onUpdateOrchestration={updateOrchestration}
                                    runStepStatuses={runStepStatuses}
                                />
                            </ReactFlowProvider>
                        </div>

                        {/* Step config panel */}
                        {selectedStep && (
                            <StepConfigPanel
                                step={selectedStep}
                                agents={agents}
                                allStepIds={allStepIds}
                                onUpdate={updateStep}
                                onDelete={() => deleteStep(selectedStep.id)}
                                onClose={() => setSelectedStepId(null)}
                                isEntry={draft.entry_step_id === selectedStep.id}
                                onSetEntry={() => setEntryPoint(selectedStep.id)}
                                availableModels={availableModels}
                            />
                        )}
                    </div>

                    {/* Bottom panel: state schema + guardrails + run log */}
                    <div className="border-t border-zinc-700 bg-zinc-900 shrink-0">
                        <BottomPanel
                            draft={draft}
                            setDraft={setDraft}
                            runStatus={runStatus}
                            liveActivity={liveActivity}
                            runLog={runLog}
                            runInput={runInput}
                            setRunInput={setRunInput}
                            onStartRun={startRun}
                            humanPrompt={humanPrompt}
                            humanContext={humanContext}
                            humanResponse={humanResponse}
                            setHumanResponse={setHumanResponse}
                            onSubmitHuman={submitHumanInput}
                            onOpenResponseModal={setResponseModal}
                            runId={runId}
                            onResumeRun={resumeRun}
                            pastRuns={pastRuns}
                            onRestoreRun={restoreRun}
                        />
                    </div>

                    {/* Response detail modal */}
                    {responseModal && (
                        <ResponseModal
                            stepName={responseModal.step_name}
                            stepType={responseModal.step_type}
                            content={responseModal.content}
                            onClose={() => setResponseModal(null)}
                        />
                    )}
                </div>
            )}

            <ConfirmationModal
                isOpen={!!confirmDeleteOrchId}
                title="Delete Orchestration"
                message="Are you sure you want to delete this orchestration? This action cannot be undone."
                onConfirm={() => {
                    confirmDeleteOrchestration();
                    setConfirmDeleteOrchId(null);
                }}
                onClose={() => setConfirmDeleteOrchId(null)}
            />

            <BuilderPanel
                isOpen={builderOpen}
                onClose={() => setBuilderOpen(false)}
                agents={agents}
                availableModels={availableModels}
                currentOrchestrationId={
                    // Only pass a real saved orchestration ID — not the temp frontend draft ID
                    selectedOrchId && orchestrations.some(o => o.id === selectedOrchId)
                        ? selectedOrchId
                        : null
                }
                sessionKey={builderSessionKey}
                onOrchestrationSaved={async (orch) => {
                    // Immediately update with the event data so user sees it
                    setOrchestrations((prev) => {
                        const idx = prev.findIndex((o) => o.id === orch.id);
                        return idx >= 0
                            ? prev.map((o) => (o.id === orch.id ? orch : o))
                            : [...prev, orch];
                    });
                    setDraft(orch);
                    setSelectedOrchId(orch.id);

                    // Re-fetch the full orchestration from backend to get the
                    // canonical version with all steps properly resolved
                    try {
                        const res = await fetch('/api/orchestrations');
                        if (res.ok) {
                            const all = await res.json();
                            const freshList = Array.isArray(all)
                                ? all.filter((o: any) => o.id !== 'orch_native_builder')
                                : [];
                            setOrchestrations(freshList);
                            const fresh = freshList.find((o: any) => o.id === orch.id);
                            if (fresh) {
                                setDraft(fresh);
                            }
                        }
                    } catch { /* use event data as fallback */ }
                }}
                onAgentSaved={(agent) => {
                    setAgents((prev) => {
                        const idx = prev.findIndex((a) => a.id === agent.id);
                        return idx >= 0
                            ? prev.map((a) => (a.id === agent.id ? agent : a))
                            : [...prev, agent];
                    });
                }}
            />
        </div>
    );
}

// --- Response detail modal ---
function ResponseModal({ stepName, stepType, content, onClose }: { stepName: string; stepType?: string; content: string; onClose: () => void }) {
    // Try to pretty-print JSON for extract_json steps
    const isJson = stepType === 'extract_json';
    let formattedJson = content;
    let jsonParseOk = false;
    if (isJson) {
        try {
            const parsed = JSON.parse(content);
            formattedJson = JSON.stringify(parsed, null, 2);
            jsonParseOk = true;
        } catch {
            // content may already be pretty or non-JSON — just display as-is
            formattedJson = content;
        }
    }
    const [copied, setCopied] = useState(false);
    useEffect(() => {
        const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [onClose]);

    return createPortal(
        <div
            className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
            {/* Panel */}
            <div className="relative z-10 w-full max-w-3xl max-h-[80vh] flex flex-col rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-700 shrink-0">
                    <div className="flex items-center gap-2">
                        <Bot size={14} className="text-blue-400" />
                        <span className="text-sm font-semibold text-zinc-100">{stepName}</span>
                        <span className="text-xs text-zinc-500">— full response</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => { navigator.clipboard.writeText(isJson ? formattedJson : content); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
                            className="text-zinc-400 hover:text-zinc-100 transition-colors p-1 rounded hover:bg-zinc-700"
                            title="Copy to clipboard"
                        >
                            {copied ? <Check size={15} className="text-green-400" /> : <Copy size={15} />}
                        </button>
                        <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors p-1 rounded hover:bg-zinc-700">
                            <X size={15} />
                        </button>
                    </div>
                </div>
                {/* Content */}
                <div className="flex-1 overflow-y-auto p-5">
                    {isJson ? (
                        /* Pretty-printed JSON with basic syntax colouring */
                        <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all rounded-lg bg-zinc-800/70 border border-zinc-700/50 p-4 overflow-x-auto">
                            {(jsonParseOk ? formattedJson : content)
                                .split('\n')
                                .map((line, i) => {
                                    /* Colour keys orange, strings lime, numbers/booleans/null cyan */
                                    const coloured = line
                                        .replace(/("(?:[^"\\]|\\.)*")(\s*:)/g, '<span class="text-orange-300">$1</span><span class="text-zinc-400">$2</span>')
                                        .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="text-lime-300">$1</span>')
                                        .replace(/:\s*(\d+\.?\d*)/g, ': <span class="text-cyan-300">$1</span>')
                                        .replace(/:\s*(true|false|null)\b/g, ': <span class="text-cyan-400">$1</span>');
                                    return (
                                        <span key={i} dangerouslySetInnerHTML={{ __html: coloured + '\n' }} />
                                    );
                                })}
                        </pre>
                    ) : (
                    <div className="prose prose-sm prose-invert max-w-none text-zinc-300 text-sm leading-relaxed">
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                                p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                                h1: ({ children }) => <h1 className="text-lg font-bold text-zinc-100 mb-2 mt-4 first:mt-0">{children}</h1>,
                                h2: ({ children }) => <h2 className="text-base font-semibold text-zinc-100 mb-2 mt-3">{children}</h2>,
                                h3: ({ children }) => <h3 className="text-sm font-semibold text-zinc-200 mb-1 mt-2">{children}</h3>,
                                ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>,
                                ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>,
                                li: ({ children }) => <li className="text-zinc-300">{children}</li>,
                                code: ({ children, className }) => {
                                    const isBlock = className?.includes('language-');
                                    return isBlock
                                        ? <code className={`block bg-zinc-800 rounded px-3 py-2 text-xs font-mono text-zinc-200 overflow-x-auto ${className}`}>{children}</code>
                                        : <code className="bg-zinc-800 px-1.5 py-0.5 rounded text-xs font-mono text-emerald-300">{children}</code>;
                                },
                                pre: ({ children }) => <pre className="bg-zinc-800/60 rounded-lg p-3 mb-3 overflow-x-auto border border-zinc-700/50">{children}</pre>,
                                blockquote: ({ children }) => <blockquote className="border-l-2 border-zinc-600 pl-3 text-zinc-400 italic">{children}</blockquote>,
                                a: ({ href, children }) => <a href={href} className="text-blue-400 underline hover:text-blue-300" target="_blank" rel="noreferrer">{children}</a>,
                                strong: ({ children }) => <strong className="font-semibold text-zinc-100">{children}</strong>,
                                em: ({ children }) => <em className="italic text-zinc-300">{children}</em>,
                                hr: () => <hr className="border-zinc-700 my-4" />,
                                table: ({ children }) => <table className="w-full text-xs border-collapse mb-3">{children}</table>,
                                th: ({ children }) => <th className="border border-zinc-700 px-2 py-1 text-zinc-200 font-semibold bg-zinc-800">{children}</th>,
                                td: ({ children }) => <td className="border border-zinc-700 px-2 py-1 text-zinc-300">{children}</td>,
                            }}
                        >
                            {content}
                        </ReactMarkdown>
                    </div>
                    )}
                </div>
            </div>
        </div>,
        document.body
    );
}

// --- Bottom panel with collapsible sections ---
function BottomPanel({
    draft, setDraft, runStatus, liveActivity, runLog, runInput, setRunInput, onStartRun,
    humanPrompt, humanContext, humanResponse, setHumanResponse, onSubmitHuman, onOpenResponseModal,
    runId, onResumeRun, pastRuns, onRestoreRun,
}: {
    draft: Orchestration;
    setDraft: (o: Orchestration) => void;
    runStatus: string;
    liveActivity: string | null;
    runLog: LogEntry[];
    runInput: string;
    setRunInput: (v: string) => void;
    onStartRun: () => void;
    humanPrompt: string | null;
    humanContext: string | null;
    humanResponse: string;
    setHumanResponse: (v: string) => void;
    onSubmitHuman: () => void;
    onOpenResponseModal: (entry: { step_name: string; step_type?: string; content: string }) => void;
    runId: string | null;
    onResumeRun: () => void;
    pastRuns: { run_id: string; orchestration_id: string; status: string; started_at?: string | null; ended_at?: string | null }[];
    onRestoreRun: (run: { run_id: string; orchestration_id: string; status: string }) => void;
}) {
    const [activeSection, setActiveSection] = useState<'state' | 'guardrails' | 'run' | 'recent'>('run');
    const [panelHeight, setPanelHeight] = useState(280);
    const [humanContextHeight, setHumanContextHeight] = useState(200);
    const logRef = useRef<HTMLDivElement>(null);
    const dragRef = useRef<{ startY: number; startHeight: number } | null>(null);
    const contextDragRef = useRef<{ startY: number; startHeight: number } | null>(null);

    const onDragHandleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        dragRef.current = { startY: e.clientY, startHeight: panelHeight };
        const onMouseMove = (ev: MouseEvent) => {
            if (!dragRef.current) return;
            const delta = dragRef.current.startY - ev.clientY;
            const newHeight = Math.max(120, Math.min(700, dragRef.current.startHeight + delta));
            setPanelHeight(newHeight);
        };
        const onMouseUp = () => {
            dragRef.current = null;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }, [panelHeight]);

    const onContextDragMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        contextDragRef.current = { startY: e.clientY, startHeight: humanContextHeight };
        const onMouseMove = (ev: MouseEvent) => {
            if (!contextDragRef.current) return;
            const delta = ev.clientY - contextDragRef.current.startY;
            const newHeight = Math.max(80, Math.min(500, contextDragRef.current.startHeight + delta));
            setHumanContextHeight(newHeight);
        };
        const onMouseUp = () => {
            contextDragRef.current = null;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }, [humanContextHeight]);

    useEffect(() => {
        if (logRef.current) {
            logRef.current.scrollTop = logRef.current.scrollHeight;
        }
    }, [runLog]);

    return (
        <div style={{ height: panelHeight }} className="flex flex-col">
            {/* Drag handle */}
            <div
                onMouseDown={onDragHandleMouseDown}
                className="h-1.5 w-full cursor-row-resize bg-zinc-800 hover:bg-blue-500/40 transition-colors flex-shrink-0 group flex items-center justify-center"
            >
                <div className="w-8 h-0.5 rounded bg-zinc-600 group-hover:bg-blue-400 transition-colors" />
            </div>
            {/* Section tabs */}
            <div className="flex border-b border-zinc-800 flex-shrink-0">
                {(['state', 'guardrails', 'run'] as const).map(section => (
                    <button
                        key={section}
                        onClick={() => setActiveSection(section)}
                        className={`px-4 py-2 text-xs font-medium capitalize transition-colors ${
                            activeSection === section
                                ? 'text-blue-400 border-b-2 border-blue-400'
                                : 'text-zinc-500 hover:text-zinc-300'
                        }`}
                    >
                        {section === 'state' ? 'State Schema' : section === 'guardrails' ? 'Guardrails' : 'Run Log'}
                        {section === 'run' && runStatus !== 'idle' && (
                            <span className={`ml-2 inline-block w-2 h-2 rounded-full ${
                                runStatus === 'running' ? 'bg-blue-400 animate-pulse' :
                                runStatus === 'completed' ? 'bg-green-400' :
                                runStatus === 'paused' ? 'bg-yellow-400' :
                                runStatus === 'cancelled' ? 'bg-zinc-500' : 'bg-red-400'
                            }`} />
                        )}
                    </button>
                ))}
                <button
                    onClick={() => setActiveSection('recent')}
                    className={`px-4 py-2 text-xs font-medium transition-colors ${
                        activeSection === 'recent'
                            ? 'text-blue-400 border-b-2 border-blue-400'
                            : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                >
                    Recent Runs
                    {pastRuns.length > 0 && (
                        <span className="ml-1.5 text-[10px] bg-zinc-700 text-zinc-400 rounded-full px-1.5 py-0.5">
                            {pastRuns.length}
                        </span>
                    )}
                </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto min-h-0">
                {/* State Schema */}
                {activeSection === 'state' && (
                    <StateSchemaEditor
                        schema={draft.state_schema}
                        onChange={(schema) => setDraft({ ...draft, state_schema: schema })}
                    />
                )}

                {/* Guardrails */}
                {activeSection === 'guardrails' && (
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <label className="text-xs text-zinc-400 block mb-1">Max Total Turns</label>
                            <input
                                type="number"
                                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 outline-none"
                                value={draft.max_total_turns}
                                onChange={(e) => setDraft({ ...draft, max_total_turns: parseInt(e.target.value) || 100 })}
                            />
                        </div>
                        <div>
                            <label className="text-xs text-zinc-400 block mb-1">Timeout (minutes)</label>
                            <input
                                type="number"
                                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 outline-none"
                                value={draft.timeout_minutes}
                                onChange={(e) => setDraft({ ...draft, timeout_minutes: parseInt(e.target.value) || 30 })}
                            />
                        </div>
                        <div>
                            <label className="text-xs text-zinc-400 block mb-1">Max Cost (USD)</label>
                            <input
                                type="number"
                                step="0.01"
                                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 outline-none"
                                value={draft.max_total_cost_usd ?? ''}
                                onChange={(e) => setDraft({ ...draft, max_total_cost_usd: e.target.value ? parseFloat(e.target.value) : null })}
                                placeholder="No limit"
                            />
                        </div>
                    </div>
                )}

                {/* Recent Runs */}
                {activeSection === 'recent' && (
                    <div className="space-y-1">
                        {pastRuns.length === 0 ? (
                            <div className="text-zinc-600 italic text-xs">No runs yet.</div>
                        ) : (
                            pastRuns.slice(0, 20).map(r => (
                                <div key={r.run_id} className="flex items-center gap-2 text-[11px] py-1 px-2 rounded bg-zinc-800/50">
                                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                        r.status === 'completed' ? 'bg-green-400' :
                                        r.status === 'failed'    ? 'bg-red-400' :
                                        r.status === 'cancelled' ? 'bg-zinc-500' :
                                        r.status === 'paused'    ? 'bg-yellow-400' : 'bg-blue-400 animate-pulse'
                                    }`} />
                                    <span className="text-zinc-400 truncate flex-1" title={r.run_id}>{r.run_id}</span>
                                    <span className="text-zinc-500 capitalize">{r.status}</span>
                                    {r.started_at && (
                                        <span className="text-zinc-600 text-[10px]">
                                            {new Date(r.started_at).toLocaleTimeString()}
                                        </span>
                                    )}
                                    {(r.status === 'failed' || r.status === 'cancelled') && (
                                        <button
                                            onClick={() => { onRestoreRun(r); setActiveSection('run'); }}
                                            className="px-2 py-0.5 text-[10px] bg-orange-600 hover:bg-orange-500 text-white rounded"
                                        >
                                            Resume
                                        </button>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                )}

                {/* Run Log */}
                {activeSection === 'run' && (
                    <div className="space-y-2">
                        {/* Input bar */}
                        {(runStatus === 'idle' || runStatus === 'completed' || runStatus === 'failed' || runStatus === 'cancelled') && (
                            <div className="flex gap-2">
                                <input
                                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-200 outline-none"
                                    value={runInput}
                                    onChange={(e) => setRunInput(e.target.value)}
                                    placeholder="Initial input for the orchestration..."
                                    onKeyDown={(e) => { if (e.key === 'Enter') onStartRun(); }}
                                />
                                {(runStatus === 'failed' || runStatus === 'cancelled') && runId && (
                                    <button
                                        onClick={onResumeRun}
                                        className="px-3 py-1.5 text-xs bg-orange-600 hover:bg-orange-500 text-white rounded whitespace-nowrap"
                                    >
                                        Resume from failure
                                    </button>
                                )}
                            </div>
                        )}

                        {/* Human input prompt */}
                        {humanPrompt && (
                            <div className="bg-amber-900/20 border border-amber-700/50 rounded p-3 space-y-2">
                                {humanContext && (
                                    <div>
                                        <div
                                            className="text-xs text-zinc-300 bg-zinc-800/60 rounded-t p-2 overflow-y-auto border border-zinc-700/50 border-b-0"
                                            style={{ height: humanContextHeight }}
                                        >
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={{
                                                    p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
                                                    a: ({ href, children }) => <a href={href} className="text-blue-400 underline" target="_blank" rel="noreferrer">{children}</a>,
                                                    code: ({ children }) => <code className="bg-zinc-700 px-1 rounded">{children}</code>,
                                                    strong: ({ children }) => <strong className="font-semibold text-zinc-100">{children}</strong>,
                                                }}
                                            >{humanContext}</ReactMarkdown>
                                        </div>
                                        <div
                                            onMouseDown={onContextDragMouseDown}
                                            className="h-1.5 w-full cursor-row-resize bg-zinc-700/60 hover:bg-blue-500/40 transition-colors rounded-b border border-zinc-700/50 flex items-center justify-center group"
                                        >
                                            <div className="w-8 h-0.5 rounded bg-zinc-600 group-hover:bg-blue-400 transition-colors" />
                                        </div>
                                    </div>
                                )}
                                <div className="text-xs text-amber-300">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            p: ({ children }) => <p className="mb-0">{children}</p>,
                                            a: ({ href, children }) => <a href={href} className="text-amber-200 underline" target="_blank" rel="noreferrer">{children}</a>,
                                            strong: ({ children }) => <strong className="font-semibold text-amber-200">{children}</strong>,
                                        }}
                                    >{humanPrompt}</ReactMarkdown>
                                </div>
                                <div className="flex gap-2">
                                    <input
                                        className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-200 outline-none"
                                        value={humanResponse}
                                        onChange={(e) => setHumanResponse(e.target.value)}
                                        placeholder="Your response..."
                                        onKeyDown={(e) => { if (e.key === 'Enter') onSubmitHuman(); }}
                                    />
                                    <button
                                        onClick={onSubmitHuman}
                                        className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded"
                                    >
                                        Submit
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Live activity: what the model is doing right now */}
                        {runStatus === 'running' && liveActivity && (
                            <div className="flex items-center gap-2 text-[11px] text-sky-300/90 bg-sky-950/30 border border-sky-900/40 rounded px-2.5 py-1.5">
                                <Loader2 size={11} className="animate-spin shrink-0" />
                                <span className="truncate">{liveActivity}</span>
                            </div>
                        )}

                        {/* Log output */}
                        <div ref={logRef} className="font-mono text-[11px] text-zinc-400 space-y-0.5">
                            {runLog.length === 0 ? (
                                <div className="text-zinc-600 italic">No run output yet. Click Run to start.</div>
                            ) : (
                                runLog.map((entry, i) => {
                                    if (typeof entry !== 'string') {
                                        if (entry.kind === 'tool_call') {
                                            return (
                                                <div key={i} className="text-violet-400 pl-2">
                                                    <details>
                                                        <summary className="cursor-pointer list-none">
                                                            🔧 {entry.tool_name}
                                                            {entry.step_name && <span className="text-zinc-500 text-[10px]"> · {entry.step_name}</span>}
                                                        </summary>
                                                        <pre className="bg-zinc-800/50 p-1 rounded mt-0.5 text-[10px] text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                                                            {JSON.stringify(entry.args, null, 2)}
                                                        </pre>
                                                    </details>
                                                </div>
                                            );
                                        }
                                        if (entry.kind === 'tool_result') {
                                            return (
                                                <div key={i} className="text-zinc-500 pl-4 text-[10px]">
                                                    ↳ {entry.preview.slice(0, 200)}{entry.preview.length > 200 ? '…' : ''}
                                                </div>
                                            );
                                        }
                                        if (entry.kind === 'step_result') {
                                            const preview = entry.content.slice(0, 200).replace(/\n+/g, ' ').trim();
                                            const isTruncated = entry.content.length > 200;
                                            const isAgent = entry.step_type === 'agent';
                                            const isPrint = entry.step_type === 'print';
                                            const isExtractJson = entry.step_type === 'extract_json';
                                            const dotColor = isAgent ? 'bg-emerald-400' : isPrint ? 'bg-lime-400' : isExtractJson ? 'bg-orange-400' : 'bg-teal-400';
                                            const labelColor = isAgent ? 'text-emerald-400' : isPrint ? 'text-lime-400' : isExtractJson ? 'text-orange-400' : 'text-teal-400';
                                            const typeLabel = isAgent ? 'agent response' : isPrint ? 'print output' : isExtractJson ? 'json output' : 'llm output';
                                            return (
                                                <div key={i} className="my-1.5">
                                                    {/* Header label */}
                                                    <div className="flex items-center gap-1.5 mb-1 pl-1">
                                                        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
                                                        <span className={`text-[10px] font-semibold uppercase tracking-wider ${labelColor}`}>
                                                            {entry.step_name}
                                                        </span>
                                                        <span className="text-[9px] text-zinc-600 uppercase tracking-wide">
                                                            {typeLabel}
                                                        </span>
                                                    </div>
                                                    {/* Content bubble */}
                                                    <div className="flex items-start gap-2 bg-zinc-800/70 border border-zinc-700/50 rounded-lg px-3 py-2 group ml-3">
                                                        <div className="flex-1 min-w-0 text-zinc-300 leading-relaxed">
                                                            {preview}{isTruncated ? '\u2026' : ''}
                                                        </div>
                                                        <button
                                                            onClick={() => onOpenResponseModal({ step_name: entry.step_name, step_type: entry.step_type, content: entry.content })}
                                                            className="shrink-0 flex items-center gap-1 text-[10px] text-zinc-500 hover:text-emerald-400 transition-colors opacity-0 group-hover:opacity-100 ml-1 whitespace-nowrap self-center"
                                                            title="View full response"
                                                        >
                                                            <ExternalLink size={10} />
                                                            View full
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        }
                                        if (entry.kind === 'reasoning' || entry.kind === 'thought') {
                                            const isReasoning = entry.kind === 'reasoning';
                                            const firstLine = entry.content.split('\n')[0].slice(0, 120);
                                            return (
                                                <div key={i} className="pl-2 my-0.5">
                                                    <details>
                                                        <summary className={`cursor-pointer list-none text-[10px] ${isReasoning ? 'text-sky-400/80' : 'text-zinc-500'}`}>
                                                            {isReasoning ? '🧠' : '💬'} {firstLine}{entry.content.length > firstLine.length ? '…' : ''}
                                                            {entry.step_name && <span className="text-zinc-600"> · {entry.step_name}</span>}
                                                        </summary>
                                                        <div className="mt-0.5 bg-zinc-800/40 border border-zinc-800 rounded p-2 text-[10px] text-zinc-400 whitespace-pre-wrap max-h-64 overflow-y-auto">
                                                            {entry.content}
                                                        </div>
                                                    </details>
                                                </div>
                                            );
                                        }
                                        return null;
                                    }
                                    return (
                                        <div key={i} className={
                                            entry.startsWith('✓') ? 'text-green-400' :
                                            entry.startsWith('✗') ? 'text-red-400' :
                                            entry.startsWith('▶') ? 'text-blue-400' :
                                            entry.startsWith('⏸') ? 'text-amber-400' :
                                            entry.startsWith('⟳') ? 'text-purple-400' :
                                            'text-zinc-400'
                                        }>
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={{
                                                    p: ({ children }) => <span>{children}</span>,
                                                    code: ({ children }) => <code className="bg-zinc-800 px-1 rounded text-[10px]">{children}</code>,
                                                    pre: ({ children }) => <pre className="bg-zinc-800 p-1 rounded mt-0.5 overflow-x-auto">{children}</pre>,
                                                    a: ({ href, children }) => <a href={href} className="underline opacity-70" target="_blank" rel="noreferrer">{children}</a>,
                                                }}
                                            >{entry}</ReactMarkdown>
                                        </div>
                                    );
                                })
                            )}
                        </div>

                    </div>
                )}
            </div>
        </div>
    );
}
