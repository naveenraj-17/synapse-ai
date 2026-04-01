'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Save, Play, Trash, Square, Loader2, Copy, Radio, Bot, Scale, GitBranch, GitMerge, RefreshCw, User, Code, Zap, Wrench } from 'lucide-react';
import { STEP_TYPE_META } from '@/types/orchestration';
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
type LogEntry = string | ToolCallLogEntry | ToolResultLogEntry;

const STEP_ICONS: Record<StepType, React.FC<{ size?: number }>> = {
    llm: Zap, agent: Bot, tool: Wrench, evaluator: Scale, parallel: GitBranch,
    merge: GitMerge, loop: RefreshCw, human: User, transform: Code, end: Square,
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

export function OrchestrationTab() {
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
    const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'paused' | 'completed' | 'failed'>('idle');
    const [runStepStatuses, setRunStepStatuses] = useState<Record<string, 'pending' | 'running' | 'paused' | 'completed' | 'failed'>>({});
    const [runId, setRunId] = useState<string | null>(null);
    const [runInput, setRunInput] = useState('');
    const [runLog, setRunLog] = useState<LogEntry[]>([]);
    const [humanPrompt, setHumanPrompt] = useState<string | null>(null);
    const [humanContext, setHumanContext] = useState<string | null>(null);
    const [humanResponse, setHumanResponse] = useState('');
    const abortRef = useRef<AbortController | null>(null);
    const [confirmDeleteOrchId, setConfirmDeleteOrchId] = useState<string | null>(null);

    // --- Active runs (for reconnect banner) ---
    const [activeRuns, setActiveRuns] = useState<Array<{
        run_id: string;
        orchestration_id: string;
        status: string;
        started_at: string | null;
    }>>([]);
    const activeRunsPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // --- Fetch orchestrations + agents ---
    useEffect(() => {
        fetch('/api/orchestrations').then(r => r.json()).then(data => {
            setOrchestrations(Array.isArray(data) ? data : []);
        }).catch(() => {});

        fetch('/api/agents').then(r => r.json()).then(data => {
            setAgents(Array.isArray(data) ? data : []);
        }).catch(() => {});

        fetch('/api/models').then(r => r.json()).then(data => {
            setAvailableModels(data.all_available || []);
        }).catch(() => {});
    }, []);

    // --- Poll active runs ---
    const fetchActiveRuns = useCallback(() => {
        fetch('/api/orchestrations/runs')
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) {
                    setActiveRuns(data.filter(r => r.status === 'running' || r.status === 'paused'));
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

    // --- Restore a run from the active runs banner ---
    const restoreRun = useCallback(async (runInfo: { run_id: string; orchestration_id: string; status: string }) => {
        const orch = orchestrations.find(o => o.id === runInfo.orchestration_id);
        setSelectedOrchId(runInfo.orchestration_id);
        setSelectedStepId(null);
        setDraft(orch ? { ...orch } : null);
        setRunId(runInfo.run_id);
        setRunStatus(runInfo.status as 'running' | 'paused' | 'completed' | 'failed');
        setRunLog([`[Reconnected to run ${runInfo.run_id}]`]);
        setHumanPrompt(null);
        setHumanContext(null);

        if (runInfo.status === 'paused') {
            try {
                const res = await fetch(`/api/orchestrations/runs/${runInfo.run_id}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.waiting_for_human && data.human_prompt) {
                        setHumanPrompt(data.human_prompt);
                    }
                }
            } catch { /* ignore */ }
        }
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
            };
            // Clean route_map entries pointing to deleted step
            if (s.route_map) {
                const newRouteMap: Record<string, string | null> = {};
                for (const [label, target] of Object.entries(s.route_map)) {
                    newRouteMap[label] = target === stepId ? null : target;
                }
                patched.route_map = newRouteMap;
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

    // --- SSE stream reader helper ---
    const streamSSE = async (url: string, body: Record<string, any>) => {
        const controller = new AbortController();
        abortRef.current = controller;

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
                const { done, value } = await reader.read();
                if (done) break;
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
            if (e.name !== 'AbortError') {
                setRunStatus('failed');
                setRunLog(prev => [...prev, '[Connection lost]']);
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

        streamSSE(`/api/orchestrations/${draft.id}/run`, { message: runInput });
    };

    const handleSSEEvent = (data: any) => {
        if (data.type && !['chunk', 'thinking', 'token_usage'].includes(data.type)) {
            console.log('[SSE]', data.type, data.orch_step_id || '', data);
        }
        switch (data.type) {
            case 'orchestration_start':
                setRunId(data.run_id);
                setRunLog(prev => [...prev, `Started run ${data.run_id}`]);
                break;

            case 'step_start':
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'running' }));
                setRunLog(prev => [...prev, `▶ ${data.step_name} (${data.step_type})`]);
                break;

            case 'step_complete':
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'completed' }));
                setRunLog(prev => [...prev, `✓ ${data.step_name} completed (${data.duration_seconds?.toFixed(1)}s)`]);
                break;

            case 'step_error':
                setRunStepStatuses(prev => ({ ...prev, [data.orch_step_id]: 'failed' }));
                setRunLog(prev => [...prev, `✗ Step error: ${data.error}`]);
                break;

            case 'routing_decision':
                setRunLog(prev => [...prev, `🔀 Evaluator routed → ${data.decision} (${data.reasoning || ''})`]);
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
                setRunStatus(data.status === 'completed' ? 'completed' : 'failed');
                setRunLog(prev => [...prev, `Done — status: ${data.status}`]);
                abortRef.current?.abort();
                abortRef.current = null;
                break;

            case 'orchestration_error':
                setRunStatus('failed');
                setRunLog(prev => [...prev, `Error: ${data.error}`]);
                abortRef.current?.abort();
                abortRef.current = null;
                break;

            case 'tool_execution':
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
                if (data.type === 'chunk' && data.content) {
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
        abortRef.current?.abort();
        abortRef.current = null;
        if (runId) {
            try {
                await fetch(`/api/orchestrations/runs/${runId}/cancel`, { method: 'POST' });
            } catch { /* ignore */ }
        }
        setRunStatus('failed');
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
        <div className="flex flex-col h-full">
            {toast && <ToastNotification show={toast.show} message={toast.message} type={toast.type} />}
            {/* Header */}
            <div className="px-6 py-4 border-b border-zinc-800 shrink-0 pr-14">
                <h1 className="text-2xl font-bold text-zinc-100">Orchestrations</h1>
                <p className="text-zinc-500 text-xs mt-0.5">Design multi-agent workflows with visual canvas</p>
            </div>

            {/* Toolbar: orchestration picker + actions */}
            <div className="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800 shrink-0">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    <select
                        className="bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 outline-none max-w-[240px]"
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
                        className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
                    >
                        <Plus size={14} /> New
                    </button>
                </div>

                {draft && (
                    <div className="flex items-center gap-2 pr-6">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded transition-colors disabled:opacity-50"
                        >
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
                        </button>
                        {runStatus === 'idle' || runStatus === 'completed' || runStatus === 'failed' ? (
                            <button
                                onClick={startRun}
                                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-600 hover:bg-green-500 text-white rounded transition-colors"
                            >
                                <Play size={14} /> Run
                            </button>
                        ) : (
                            <button
                                onClick={cancelRun}
                                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
                            >
                                <Square size={14} /> Cancel
                            </button>
                        )}
                        <button
                            onClick={handleDeploy}
                            className="px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded transition-colors"
                        >
                            Deploy as Agent
                        </button>
                        <button
                            onClick={handleDuplicate}
                            disabled={saving}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded transition-colors disabled:opacity-50"
                        >
                            <Copy size={13} /> Duplicate
                        </button>
                        <div className="w-px h-5 bg-zinc-700 mx-1" />
                        <button
                            onClick={handleDelete}
                            className="flex items-center gap-1 px-2 py-1.5 text-xs text-zinc-500 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
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
                                    className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
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
                <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
                    Select an orchestration or create a new one to get started.
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
                        {(['llm', 'agent', 'tool', 'evaluator', 'parallel', 'merge', 'loop', 'human', 'transform', 'end'] as StepType[]).map(type => {
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
                            runLog={runLog}
                            runInput={runInput}
                            setRunInput={setRunInput}
                            humanPrompt={humanPrompt}
                            humanContext={humanContext}
                            humanResponse={humanResponse}
                            setHumanResponse={setHumanResponse}
                            onSubmitHuman={submitHumanInput}
                        />
                    </div>
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
        </div>
    );
}

// --- Bottom panel with collapsible sections ---
function BottomPanel({
    draft, setDraft, runStatus, runLog, runInput, setRunInput,
    humanPrompt, humanContext, humanResponse, setHumanResponse, onSubmitHuman,
}: {
    draft: Orchestration;
    setDraft: (o: Orchestration) => void;
    runStatus: string;
    runLog: string[];
    runInput: string;
    setRunInput: (v: string) => void;
    humanPrompt: string | null;
    humanContext: string | null;
    humanResponse: string;
    setHumanResponse: (v: string) => void;
    onSubmitHuman: () => void;
}) {
    const [activeSection, setActiveSection] = useState<'state' | 'guardrails' | 'run'>('run');
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
                                runStatus === 'paused' ? 'bg-yellow-400' : 'bg-red-400'
                            }`} />
                        )}
                    </button>
                ))}
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

                {/* Run Log */}
                {activeSection === 'run' && (
                    <div className="space-y-2">
                        {/* Input bar */}
                        {(runStatus === 'idle' || runStatus === 'completed' || runStatus === 'failed') && (
                            <div className="flex gap-2">
                                <input
                                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-200 outline-none"
                                    value={runInput}
                                    onChange={(e) => setRunInput(e.target.value)}
                                    placeholder="Initial input for the orchestration..."
                                    onKeyDown={(e) => { if (e.key === 'Enter') { /* startRun triggered from top bar */ } }}
                                />
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
                                        return (
                                            <div key={i} className="text-zinc-500 pl-4 text-[10px]">
                                                ↳ {entry.preview.slice(0, 200)}{entry.preview.length > 200 ? '…' : ''}
                                            </div>
                                        );
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
