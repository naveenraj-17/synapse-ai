/* eslint-disable @typescript-eslint/no-explicit-any */
import { MutableRefObject, useEffect, useRef, useState } from 'react';
import { Wrench, Plus, Trash, X, ExternalLink } from 'lucide-react';
import { PythonToolEditor, type PythonDraftTool } from './PythonToolEditor';

interface CustomToolsTabProps {
    customTools: any[];
    draftTool: any;
    setDraftTool: (v: any) => void;
    toolBuilderMode: 'config' | 'n8n' | 'python';
    setToolBuilderMode: (v: 'config' | 'n8n' | 'python') => void;
    headerRows: { id: string; key: string; value: string }[];
    setHeaderRows: (v: { id: string; key: string; value: string }[]) => void;
    n8nWorkflows: any[];
    n8nWorkflowsLoading: boolean;
    n8nWorkflowId: string | null;
    setN8nWorkflowId: (v: string | null) => void;
    isIframeFullscreen: boolean;
    setIsIframeFullscreen: (v: boolean) => void;
    isN8nLoading: boolean;
    setIsN8nLoading: (v: boolean) => void;
    n8nIframeRef: MutableRefObject<HTMLIFrameElement | null>;
    getN8nBaseUrl: () => string;
    onSaveTool: () => void;
    onDeleteTool: (name: string) => void;
    /** True when n8n URL + API key are configured */
    n8nIntegrated: boolean;
}

export const CustomToolsTab = ({
    customTools, draftTool, setDraftTool,
    toolBuilderMode, setToolBuilderMode,
    headerRows, setHeaderRows,
    n8nWorkflows, n8nWorkflowsLoading,
    n8nWorkflowId, setN8nWorkflowId,
    isIframeFullscreen, setIsIframeFullscreen,
    isN8nLoading, setIsN8nLoading, n8nIframeRef,
    getN8nBaseUrl, onSaveTool, onDeleteTool,
    n8nIntegrated,
}: CustomToolsTabProps) => {
    // n8n iframe error state
    const [isN8nError, setIsN8nError] = useState(false);
    const n8nTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Reset error state when switching to n8n mode
    useEffect(() => {
        if (toolBuilderMode === 'n8n') {
            setIsN8nError(false);
            setIsN8nLoading(true);
            // 12-second timeout: if iframe hasn't loaded, show error
            n8nTimerRef.current = setTimeout(() => {
                setIsN8nError(true);
                setIsN8nLoading(false);
            }, 12000);
        } else {
            if (n8nTimerRef.current) clearTimeout(n8nTimerRef.current);
        }
        return () => { if (n8nTimerRef.current) clearTimeout(n8nTimerRef.current); };
    }, [toolBuilderMode, setIsN8nLoading]);

    const handleIframeLoad = () => {
        if (n8nTimerRef.current) clearTimeout(n8nTimerRef.current);
        setIsN8nLoading(false);
        setIsN8nError(false);
    };

    // ── Get tool type badge ────────────────────────────────────────────────
    const getToolBadge = (t: any) => {
        if (t.tool_type === 'python') {
            return <span className="text-[9px] font-bold bg-violet-900/40 border border-violet-700 text-violet-400 px-1.5 py-0.5 rounded">🐍 PYTHON</span>;
        }
        if (t.workflowId || t.url?.includes('webhook')) {
            return <span className="text-[9px] font-bold bg-orange-900/30 border border-orange-700/50 text-orange-400 px-1.5 py-0.5 rounded">n8n</span>;
        }
        return <span className="text-[9px] font-bold bg-zinc-800 border border-zinc-700 text-zinc-400 px-1.5 py-0.5 rounded">HTTP</span>;
    };

    return (
        <div className="flex flex-col min-h-[600px]">
            {!draftTool ? (
                /* ── List View ───────────────────────────────────────────── */
                <div className="space-y-4">
                    <div className="flex justify-between items-center">
                        <div>
                            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                                <Wrench className="h-5 w-5" /> Custom Tools
                            </h3>
                            <p className="text-zinc-500 text-sm">
                                Extend your agent with n8n webhooks, HTTP endpoints, or Python functions.
                            </p>
                        </div>
                        <button
                            onClick={() => {
                                const initialInput = { type: 'object', properties: { input: { type: 'string' } } };
                                setDraftTool({
                                    name: '',
                                    generalName: '',
                                    description: '',
                                    url: '',
                                    method: 'POST',
                                    inputSchema: initialInput,
                                    inputSchemaStr: JSON.stringify(initialInput, null, 2),
                                    outputSchemaStr: '',
                                    tool_type: 'http',
                                });
                                setHeaderRows([{ id: 'h1', key: '', value: '' }]);
                                setToolBuilderMode('config');
                            }}
                            className="px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-300 font-bold text-xs uppercase flex items-center gap-2 hover:bg-zinc-700 hover:text-white transition-colors"
                        >
                            <Plus className="h-4 w-4" /> New Tool
                        </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {customTools.map((t: any) => (
                            <div key={t.name} className={`p-4 border hover:border-zinc-600 transition-all group relative ${t.tool_type === 'python' ? 'bg-violet-950/10 border-violet-900/30 hover:border-violet-700/50' : 'bg-zinc-900 border-zinc-800'}`}>
                                <div className="font-bold text-white mb-1 flex items-center gap-2 pr-10">
                                    <span className="truncate">{t.generalName || t.name}</span>
                                    {getToolBadge(t)}
                                </div>
                                {t.generalName && <div className="text-[9px] text-zinc-500 font-mono mb-1">({t.name})</div>}
                                <div className="text-xs text-zinc-500 mb-2 h-8 overflow-hidden">{t.description}</div>
                                {t.tool_type === 'python'
                                    ? <div className="text-[10px] font-mono text-violet-600">🐍 Python sandboxed function</div>
                                    : <div className="text-[10px] font-mono text-zinc-600 truncate">{t.url}</div>
                                }
                                <button
                                    onClick={() => onDeleteTool(t.name)}
                                    className="absolute top-2 right-2 p-1 text-zinc-600 hover:text-red-500 opacity-0 group-hover:opacity-100"
                                >
                                    <Trash className="h-4 w-4" />
                                </button>
                                <button
                                    onClick={() => {
                                        if (t.tool_type === 'python') {
                                            setDraftTool({
                                                ...t,
                                                schemaParams: t.schemaParams || [],
                                            });
                                            setToolBuilderMode('python');
                                        } else {
                                            setDraftTool({
                                                ...t,
                                                inputSchemaStr: JSON.stringify(t.inputSchema || {}, null, 2),
                                                outputSchemaStr: t.outputSchema ? JSON.stringify(t.outputSchema, null, 2) : '',
                                            });
                                            const rows = Object.entries(t.headers || {}).map(([k, v], i) => ({
                                                id: `h-${i}`, key: k, value: v as string
                                            }));
                                            setHeaderRows(rows.length ? rows : [{ id: 'h1', key: '', value: '' }]);
                                            setToolBuilderMode('config');
                                        }
                                    }}
                                    className="absolute bottom-2 right-2 text-[10px] text-zinc-400 hover:text-white font-bold uppercase"
                                >
                                    Edit
                                </button>
                            </div>
                        ))}
                        {customTools.length === 0 && (
                            <div className="col-span-full py-12 text-center text-zinc-600 italic text-sm border border-dashed border-zinc-800">
                                No custom tools yet. Create an HTTP, n8n webhook, or Python tool.
                            </div>
                        )}
                    </div>
                </div>
            ) : (
                /* ── Builder View ────────────────────────────────────────── */
                <div className="flex flex-col h-full">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-4 pb-4 border-b border-zinc-800">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => { setDraftTool(null); setToolBuilderMode('config'); }}
                                className="text-zinc-500 hover:text-white"
                            >
                                <X className="h-5 w-5" />
                            </button>
                            <h3 className="font-bold text-white uppercase tracking-wider">
                                {draftTool.name ? `Editing: ${draftTool.name}` : 'New Tool Builder'}
                            </h3>
                        </div>
                        <div className="flex gap-2">
                            {/* Mode tabs */}
                            <div className="flex bg-zinc-900 border border-zinc-800 p-1 rounded gap-0.5">
                                <button
                                    onClick={() => {
                                        if (draftTool.tool_type === 'python') {
                                            const initialInput = { type: 'object', properties: { input: { type: 'string' } } };
                                            setDraftTool({ ...draftTool, tool_type: 'http', url: draftTool.url || '', method: draftTool.method || 'POST', inputSchema: initialInput, inputSchemaStr: JSON.stringify(initialInput, null, 2), outputSchemaStr: '' });
                                            setHeaderRows([{ id: 'h1', key: '', value: '' }]);
                                        }
                                        setToolBuilderMode('config');
                                    }}
                                    className={`px-3 py-1 text-xs font-bold rounded ${toolBuilderMode === 'config' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                                >
                                    CONFIG
                                </button>
                                {n8nIntegrated && (
                                    <button
                                        onClick={() => {
                                            if (draftTool.tool_type === 'python') {
                                                const initialInput = { type: 'object', properties: { input: { type: 'string' } } };
                                                setDraftTool({ ...draftTool, tool_type: 'http', url: draftTool.url || '', method: draftTool.method || 'POST', inputSchema: initialInput, inputSchemaStr: JSON.stringify(initialInput, null, 2), outputSchemaStr: '' });
                                                setHeaderRows([{ id: 'h1', key: '', value: '' }]);
                                            }
                                            setToolBuilderMode('n8n');
                                        }}
                                        className={`px-3 py-1 text-xs font-bold rounded ${toolBuilderMode === 'n8n' ? 'bg-[#ff6d5a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                                    >
                                        n8n BUILDER
                                    </button>
                                )}
                                <button
                                    onClick={() => {
                                        if (draftTool.tool_type !== 'python') {
                                            const defaultCode = `# _args contains all tool arguments as a Python dict\n# print() stdout becomes the tool result\nimport json\n\nresult = {"output": _args.get("input", "")}\nprint(json.dumps(result))\n`;
                                            setDraftTool({ ...draftTool, tool_type: 'python', code: draftTool.code || defaultCode, inputSchema: { type: 'object', properties: { input: { type: 'string' } } }, schemaParams: draftTool.schemaParams || [{ id: 'p1', name: 'input', type: 'string', description: 'The input value', required: false }] });
                                        }
                                        setToolBuilderMode('python');
                                    }}
                                    className={`px-3 py-1 text-xs font-bold rounded ${toolBuilderMode === 'python' ? 'bg-violet-700 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                                >
                                    🐍 PYTHON
                                </button>
                            </div>
                            <button
                                onClick={onSaveTool}
                                className="px-4 py-1.5 bg-white text-black text-xs font-bold hover:bg-zinc-200"
                            >
                                SAVE
                            </button>
                        </div>
                    </div>

                    {/* Shared name / description fields */}
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="space-y-1">
                            <label className="text-[10px] uppercase font-bold text-zinc-500">General Name</label>
                            <input
                                type="text"
                                value={draftTool.generalName || ''}
                                onChange={e => {
                                    const val = e.target.value;
                                    const update: any = { ...draftTool, generalName: val };
                                    if (!draftTool.name) {
                                        update.name = val.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
                                    }
                                    setDraftTool(update);
                                }}
                                className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700"
                                placeholder="e.g. Process Orders"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-[10px] uppercase font-bold text-zinc-500">System Name (Snake Case)</label>
                            <input
                                type="text"
                                value={draftTool.name}
                                onChange={e => setDraftTool({ ...draftTool, name: e.target.value })}
                                className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700"
                                placeholder="e.g. process_orders"
                            />
                        </div>
                    </div>
                    <div className="space-y-1 mb-5">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Description (For AI)</label>
                        <textarea
                            value={draftTool.description}
                            onChange={e => setDraftTool({ ...draftTool, description: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none resize-vertical min-h-[80px]"
                            placeholder="What does this tool do? Describe its purpose and critical rules for the AI..."
                        />
                    </div>

                    {/* ── CONFIG mode (HTTP/n8n tool) ────────────────────── */}
                    {toolBuilderMode === 'config' && (
                        <div className="space-y-5 pr-2">
                            {/* Method */}
                            <div className="space-y-1">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Method</label>
                                <select
                                    value={draftTool.method}
                                    onChange={e => setDraftTool({ ...draftTool, method: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none"
                                >
                                    <option>POST</option>
                                    <option>GET</option>
                                </select>
                            </div>

                            {/* n8n Workflow — only shown when n8n is integrated */}
                            {n8nIntegrated && (
                                <div className="space-y-1">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">n8n Workflow</label>
                                    <select
                                        value={draftTool.workflowId || ''}
                                        onChange={async (e) => {
                                            const workflowId = e.target.value;
                                            setDraftTool({ ...draftTool, workflowId });
                                            setN8nWorkflowId(workflowId || null);
                                            if (!workflowId) return;
                                            try {
                                                const res = await fetch(`/api/n8n/workflows/${workflowId}/webhook`);
                                                if (!res.ok) return;
                                                const data = await res.json();
                                                if (data?.productionUrl) {
                                                    setDraftTool({ ...draftTool, workflowId, url: data.productionUrl });
                                                }
                                            } catch { /* ignore */ }
                                        }}
                                        className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none"
                                    >
                                        <option value="">{n8nWorkflowsLoading ? 'Loading workflows...' : 'Select a workflow (optional)'}</option>
                                        {Array.isArray(n8nWorkflows) && n8nWorkflows.map((w: any) => (
                                            <option key={String(w.id)} value={String(w.id)}>
                                                {w.name || w.id}
                                            </option>
                                        ))}
                                    </select>
                                    <p className="text-[10px] text-zinc-600">
                                        Selecting a workflow auto-fills the Webhook URL below.
                                    </p>
                                </div>
                            )}

                            {/* Webhook URL */}
                            <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Webhook URL</label>
                                    {!n8nIntegrated && (
                                        <span className="text-[9px] text-zinc-600">
                                            (
                                            <a href="/settings/workspace" className="text-[#ff6d5a] hover:underline">
                                                Connect n8n
                                            </a>
                                            {' '}for auto-fill)
                                        </span>
                                    )}
                                </div>
                                <input
                                    type="text"
                                    value={draftTool.url}
                                    onChange={e => setDraftTool({ ...draftTool, url: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono"
                                    placeholder="https://your-n8n.com/webhook/..."
                                />
                            </div>

                            {/* Headers */}
                            <div className="space-y-2 pt-2">
                                <div className="flex justify-between items-end mb-1">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Headers</label>
                                    <button
                                        onClick={() => setHeaderRows([...headerRows, { id: `h-${Date.now()}`, key: '', value: '' }])}
                                        className="text-[10px] text-zinc-400 hover:text-white font-bold bg-zinc-800 px-2 py-1 rounded transition-colors"
                                    >
                                        + ADD HEADER
                                    </button>
                                </div>
                                {headerRows.map((row, idx) => (
                                    <div key={row.id} className="flex gap-2 items-center">
                                        <input
                                            type="text"
                                            placeholder="Key (e.g. Authorization)"
                                            value={row.key}
                                            onChange={e => {
                                                const newRows = [...headerRows];
                                                newRows[idx].key = e.target.value;
                                                setHeaderRows(newRows);
                                            }}
                                            className="flex-1 bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono"
                                        />
                                        <input
                                            type="text"
                                            placeholder="Value"
                                            value={row.value}
                                            onChange={e => {
                                                const newRows = [...headerRows];
                                                newRows[idx].value = e.target.value;
                                                setHeaderRows(newRows);
                                            }}
                                            className="flex-1 bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono"
                                        />
                                        <button
                                            onClick={() => setHeaderRows(headerRows.filter(r => r.id !== row.id))}
                                            className="p-2 text-zinc-600 hover:text-red-500 transition-colors"
                                        >
                                            <Trash className="h-4 w-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>

                            {/* Schemas */}
                            <div className="grid grid-cols-2 gap-4 flex-1 min-h-0">
                                <div className="space-y-1 flex flex-col min-h-[280px]">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Input Schema (JSON)</label>
                                    <textarea
                                        value={draftTool.inputSchemaStr}
                                        onChange={e => setDraftTool({ ...draftTool, inputSchemaStr: e.target.value })}
                                        className="w-full flex-1 bg-zinc-950 border border-zinc-800 p-3 text-[10px] font-mono text-zinc-300 focus:border-white focus:outline-none resize-none"
                                        placeholder='{"type": "object", "properties": {"msg": {"type": "string"}}}'
                                    />
                                </div>
                                <div className="space-y-1 flex flex-col min-h-[280px]">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Output Schema (JSON)</label>
                                    <textarea
                                        value={draftTool.outputSchemaStr}
                                        onChange={e => setDraftTool({ ...draftTool, outputSchemaStr: e.target.value })}
                                        className="w-full flex-1 bg-zinc-900 border border-zinc-800 p-3 text-[10px] font-mono text-zinc-300 focus:border-white focus:outline-none resize-none"
                                        placeholder='(Optional) {"properties": {"id": {"type": "string"}}} - Filters response to these keys.'
                                    />
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── n8n BUILDER mode ──────────────────────────────── */}
                    {toolBuilderMode === 'n8n' && (
                        <div className="h-[600px] bg-white relative overflow-hidden border border-zinc-800">
                            {/* Workflow ID Display */}
                            {draftTool.workflowId && (
                                <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2 bg-zinc-900 border border-zinc-700 p-1.5 rounded shadow-lg">
                                    <div className="px-1 text-[10px] font-bold text-zinc-500 uppercase tracking-wider">ID:</div>
                                    <code className="text-xs text-white font-mono">{draftTool.workflowId}</code>
                                    <button
                                        onClick={() => navigator.clipboard.writeText(draftTool.workflowId || '')}
                                        className="p-1 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded"
                                        title="Copy ID"
                                    >
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                    </button>
                                </div>
                            )}

                            {/* Fullscreen toggle */}
                            <button
                                onClick={() => setIsIframeFullscreen(!isIframeFullscreen)}
                                className="absolute bottom-4 right-4 z-20 p-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded border border-zinc-700 flex items-center gap-2 text-xs font-bold shadow-lg"
                            >
                                {isIframeFullscreen ? (
                                    <><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>Exit Fullscreen</>
                                ) : (
                                    <><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>Fullscreen</>
                                )}
                            </button>

                            {/* Loading / error state */}
                            {!isIframeFullscreen && (isN8nLoading || isN8nError) && (
                                <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10">
                                    {isN8nError ? (
                                        <div className="text-center max-w-sm">
                                            <div className="text-3xl mb-3">⚠️</div>
                                            <p className="font-bold text-zinc-800 mb-1">Cannot reach n8n</p>
                                            <p className="text-zinc-500 text-xs mb-3">
                                                Make sure n8n is running at{' '}
                                                <code className="bg-zinc-100 px-1 text-zinc-700">{getN8nBaseUrl()}</code>
                                            </p>
                                            <a
                                                href={getN8nBaseUrl()}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="inline-flex items-center gap-1 text-xs text-[#ff6d5a] hover:underline"
                                            >
                                                Open n8n <ExternalLink className="h-3 w-3" />
                                            </a>
                                        </div>
                                    ) : (
                                        <div className="text-center text-black/50">
                                            <p className="font-bold animate-pulse">Loading n8n Editor...</p>
                                            <p className="text-xs mt-1">Connecting to {getN8nBaseUrl()}</p>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* n8n iframe */}
                            {!isIframeFullscreen && !isN8nError && (
                                <iframe
                                    onLoad={handleIframeLoad}
                                    src={(() => {
                                        const base = getN8nBaseUrl();
                                        if (draftTool?.workflowId) return `${base}/workflow/${draftTool.workflowId}`;
                                        return `${base}/workflow/new`;
                                    })()}
                                    ref={n8nIframeRef}
                                    className="w-full h-full z-0"
                                    title="n8n Editor"
                                    allow="clipboard-read; clipboard-write"
                                    sandbox="allow-forms allow-modals allow-popups allow-presentation allow-same-origin allow-scripts"
                                />
                            )}
                        </div>
                    )}

                    {/* ── PYTHON mode ────────────────────────────────────── */}
                    {toolBuilderMode === 'python' && (
                        <PythonToolEditor
                            draft={draftTool as PythonDraftTool}
                            onChange={(updated) => setDraftTool(updated)}
                        />
                    )}
                </div>
            )}
        </div>
    );
};
