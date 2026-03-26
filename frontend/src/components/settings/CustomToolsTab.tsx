/* eslint-disable @typescript-eslint/no-explicit-any */
import { MutableRefObject } from 'react';
import { Wrench, Plus, Trash, X } from 'lucide-react';

interface CustomToolsTabProps {
    customTools: any[];
    draftTool: any;
    setDraftTool: (v: any) => void;
    toolBuilderMode: 'config' | 'n8n';
    setToolBuilderMode: (v: 'config' | 'n8n') => void;
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
}

export const CustomToolsTab = ({
    customTools, draftTool, setDraftTool,
    toolBuilderMode, setToolBuilderMode,
    headerRows, setHeaderRows,
    n8nWorkflows, n8nWorkflowsLoading,
    n8nWorkflowId, setN8nWorkflowId,
    isIframeFullscreen, setIsIframeFullscreen,
    isN8nLoading, setIsN8nLoading, n8nIframeRef,
    getN8nBaseUrl, onSaveTool, onDeleteTool
}: CustomToolsTabProps) => (
    <div className="flex flex-col min-h-[600px]">
        {!draftTool ? (
            /* List View */
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <div>
                        <h3 className="text-lg font-bold text-white flex items-center gap-2">
                            <Wrench className="h-5 w-5" /> Custom Tools
                        </h3>
                        <p className="text-zinc-500 text-sm">Extend your agent with n8n workflows or webhooks.</p>
                    </div>
                    <button
                        onClick={() => {
                            const initialInput = { type: "object", properties: { input: { type: "string" } } };
                            setDraftTool({
                                name: "",
                                generalName: "",
                                description: "",
                                url: "",
                                method: "POST",
                                inputSchema: initialInput,
                                inputSchemaStr: JSON.stringify(initialInput, null, 2),
                                outputSchemaStr: ""
                            });
                            setHeaderRows([{ id: 'h1', key: '', value: '' }]);
                        }}
                        className="px-4 py-2 bg-white text-black font-bold text-xs uppercase flex items-center gap-2 hover:bg-zinc-200"
                    >
                        <Plus className="h-4 w-4" /> Create Tool
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {customTools.map((t: any) => (
                        <div key={t.name} className="p-4 bg-zinc-900 border border-zinc-800 hover:border-zinc-600 transition-all group relative">
                            <div className="font-bold text-white mb-1 flex items-center gap-2">
                                {t.generalName || t.name}
                                {t.generalName && <span className="text-[9px] text-zinc-500 font-normal">({t.name})</span>}
                            </div>
                            <div className="text-xs text-zinc-500 mb-2 h-8 overflow-hidden">{t.description}</div>
                            <div className="text-[10px] font-mono text-zinc-600 truncate">{t.url}</div>
                            <button
                                onClick={() => onDeleteTool(t.name)}
                                className="absolute top-2 right-2 p-1 text-zinc-600 hover:text-red-500 opacity-0 group-hover:opacity-100"
                            >
                                <Trash className="h-4 w-4" />
                            </button>
                            <button
                                onClick={() => {
                                    setDraftTool({
                                        ...t,
                                        inputSchemaStr: JSON.stringify(t.inputSchema || {}, null, 2),
                                        outputSchemaStr: t.outputSchema ? JSON.stringify(t.outputSchema, null, 2) : ""
                                    });
                                    // Populate headers
                                    const rows = Object.entries(t.headers || {}).map(([k, v], i) => ({
                                        id: `h-${i}`,
                                        key: k,
                                        value: v as string
                                    }));
                                    setHeaderRows(rows.length ? rows : [{ id: 'h1', key: '', value: '' }]);
                                }}
                                className="absolute bottom-2 right-2 text-[10px] text-zinc-400 hover:text-white font-bold uppercase"
                            >
                                Edit
                            </button>
                        </div>
                    ))}
                    {customTools.length === 0 && (
                        <div className="col-span-full py-12 text-center text-zinc-600 italic text-sm border border-dashed border-zinc-800">
                            No custom tools yet. Build one to connect n8n!
                        </div>
                    )}
                </div>
            </div>
        ) : (
            /* Builder View */
            <div className="flex flex-col h-full">
                <div className="flex items-center justify-between mb-4 pb-4 border-b border-zinc-800">
                    <div className="flex items-center gap-4">
                        <button onClick={() => { setDraftTool(null); setToolBuilderMode('config'); }} className="text-zinc-500 hover:text-white">
                            <X className="h-5 w-5" />
                        </button>
                        <h3 className="font-bold text-white uppercase tracking-wider">
                            {draftTool.name ? `Editing: ${draftTool.name}` : 'New Tool Builder'}
                        </h3>
                    </div>
                    <div className="flex gap-2">
                        <div className="flex bg-zinc-900 border border-zinc-800 p-1 rounded">
                            <button
                                onClick={() => setToolBuilderMode('config')}
                                className={`px-3 py-1 text-xs font-bold rounded ${toolBuilderMode === 'config' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                            >
                                CONFIG
                            </button>
                            <button
                                onClick={() => setToolBuilderMode('n8n')}
                                className={`px-3 py-1 text-xs font-bold rounded ${toolBuilderMode === 'n8n' ? 'bg-[#ff6d5a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                            >
                                n8n BUILDER
                            </button>
                        </div>
                        <button onClick={onSaveTool} className="px-4 py-1.5 bg-white text-black text-xs font-bold hover:bg-zinc-200">
                            SAVE
                        </button>
                    </div>
                </div>

                {toolBuilderMode === 'config' ? (
                    <div className="space-y-6 pr-2">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">General Name</label>
                                <input type="text" value={draftTool.generalName || ''} onChange={e => {
                                    const val = e.target.value;
                                    const update: any = { ...draftTool, generalName: val };
                                    // Auto-fill snake_case functionality
                                    if (!draftTool.name) {
                                        update.name = val.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
                                    }
                                    setDraftTool(update);
                                }}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700"
                                    placeholder="e.g. Create Jira Ticket" />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">System Name (Snake Case)</label>
                                <input type="text" value={draftTool.name} onChange={e => setDraftTool({ ...draftTool, name: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700" placeholder="e.g. create_jira_ticket" />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Method</label>
                                <select value={draftTool.method} onChange={e => setDraftTool({ ...draftTool, method: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none">
                                    <option>POST</option>
                                    <option>GET</option>
                                </select>
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Tool Type</label>
                                <select value={draftTool.tool_type || 'standard'} onChange={e => setDraftTool({ ...draftTool, tool_type: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none">
                                    <option value="standard">Standard</option>
                                    <option value="report">Report (Supports RAG)</option>
                                </select>
                                <p className="text-[9px] text-zinc-500">Report tools enable dynamic RAG for analysis agents</p>
                            </div>
                        </div>

                        <div className="space-y-1 col-span-2">
                            <label className="text-[10px] uppercase font-bold text-zinc-500">Description (For AI)</label>
                            <textarea 
                                value={draftTool.description} 
                                onChange={e => setDraftTool({ ...draftTool, description: e.target.value })}
                                className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none resize-vertical min-h-[100px]"
                                placeholder="What does this tool do? Describe its purpose, workflow, and critical rules..."
                            />
                            <p className="text-[10px] text-zinc-600">Provide detailed instructions for the AI on how to use this tool correctly.</p>
                        </div>

                        {draftTool.tool_type === 'report' && (
                            <div className="space-y-1 col-span-2">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Field Descriptions (JSON)</label>
                                <textarea 
                                    value={typeof draftTool.field_descriptions === 'string' ? draftTool.field_descriptions : JSON.stringify(draftTool.field_descriptions || [], null, 2)}
                                    onChange={e => setDraftTool({ ...draftTool, field_descriptions: e.target.value })}
                                    className="w-full bg-zinc-900 border border-zinc-800 p-2 text-xs font-mono text-zinc-300 focus:border-white focus:outline-none resize-vertical min-h-[150px]"
                                    placeholder={JSON.stringify([
                                        {
                                            type: "delinquency",
                                            fields: {
                                                tenant_id: "Unique identifier for tenant",
                                                balance_due: "Outstanding balance amount"
                                            }
                                        }
                                    ], null, 2)}
                                />
                                <p className="text-[10px] text-zinc-600">Define field descriptions for each report type. Only relevant types are sent to LLM.</p>
                            </div>
                        )}


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
                                    } catch {
                                        // ignore
                                    }
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
                                Configure n8n in Integrations to enable workflow listing.
                            </p>
                        </div>

                        <div className="space-y-1">
                            <div className="flex items-center gap-2">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Webhook URL</label>
                                <div className="group relative">
                                    <svg className="w-3.5 h-3.5 text-zinc-600 hover:text-[#ff6d5a] cursor-help" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                                    </svg>
                                    {/* Tooltip */}
                                    <div className="invisible group-hover:visible absolute left-0 top-6 w-72 p-3 bg-zinc-900 border border-zinc-700 text-[10px] text-zinc-300 z-50 shadow-xl">
                                        <p className="font-bold text-[#ff6d5a] mb-2">💡 Quick Setup:</p>
                                        <ol className="list-decimal list-inside space-y-1 pl-1">
                                            <li>Click <span className="font-bold">n8n BUILDER</span> tab</li>
                                            <li>Add <span className="font-mono bg-zinc-800 px-1">Webhook</span> node</li>
                                            <li>Set webhook path</li>
                                            <li>Build workflow &amp; Save</li>
                                            <li>URL auto-populates here!</li>
                                        </ol>
                                    </div>
                                </div>
                            </div>
                            <input type="text" value={draftTool.url} onChange={e => setDraftTool({ ...draftTool, url: e.target.value })}
                                className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono"
                                placeholder="http://localhost:5678/webhook/..." />
                        </div>

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
                ) : (
                    <div className="h-[600px] bg-white relative overflow-hidden border border-zinc-800">
                        {/* Workflow ID Display - Bottom Left */}
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


                        {/* Fullscreen Toggle Button - Bottom Right */}
                        <button
                            onClick={() => setIsIframeFullscreen(!isIframeFullscreen)}
                            className="absolute bottom-4 right-4 z-20 p-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded border border-zinc-700 flex items-center gap-2 text-xs font-bold shadow-lg"
                            title={isIframeFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
                        >
                            {isIframeFullscreen ? (
                                <>
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                    Exit Fullscreen
                                </>
                            ) : (
                                <>
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                    </svg>
                                    Fullscreen
                                </>
                            )}
                        </button>

                        {/* Loading message - only show when not fullscreen */}
                        {!isIframeFullscreen && isN8nLoading && (
                            <div className="absolute inset-0 flex items-center justify-center text-black/50 z-0">
                                <div className="text-center">
                                    <p className="font-bold">Loading n8n Editor...</p>
                                    <p className="text-xs">Ensure n8n is running at {getN8nBaseUrl()}</p>
                                </div>
                            </div>
                        )}

                        {/* n8n iframe - normal view */}
                        {!isIframeFullscreen && (
                            <iframe
                                onLoad={() => setIsN8nLoading(false)}
                                src={
                                    (() => {
                                        const base = getN8nBaseUrl();
                                        if (draftTool?.workflowId) return `${base}/workflow/${draftTool.workflowId}`;
                                        return `${base}/workflow/new`;
                                    })()
                                }
                                ref={n8nIframeRef}
                                className="w-full h-full z-10"
                                title="n8n Editor"
                                allow="clipboard-read; clipboard-write"
                                sandbox="allow-forms allow-modals allow-popups allow-presentation allow-same-origin allow-scripts"
                            />
                        )}
                    </div>
                )}
            </div>
        )}
    </div>
);
