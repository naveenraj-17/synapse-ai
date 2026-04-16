'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useRef, useEffect } from 'react';
import { X, Send, Sparkles, ChevronDown, ChevronUp, Loader2, Bot, Plus } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Orchestration } from '@/types/orchestration';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ToolEntry {
    name: string;
    args?: any;
    result?: string;
}

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    kind?: 'text' | 'tool_group' | 'banner_orch' | 'banner_agent';
    tools?: ToolEntry[];
    bannerText?: string;
}

interface BuilderPanelProps {
    isOpen: boolean;
    onClose: () => void;
    agents: any[];
    availableModels: string[];
    currentOrchestrationId: string | null;
    onOrchestrationSaved: (orch: Orchestration) => void;
    onAgentSaved: (agent: any) => void;
    sessionKey?: number;
}

// ─── Tools Collapsible ────────────────────────────────────────────────────────

function ToolsCollapsible({ tools, isStreaming }: { tools: ToolEntry[]; isStreaming?: boolean }) {
    const [open, setOpen] = useState(false);
    if (!tools || tools.length === 0) return null;
    const doneCount = tools.filter((t) => t.result !== undefined).length;

    return (
        <div className="flex justify-start">
            <div className="max-w-[90%] border border-zinc-700/50 rounded-lg overflow-hidden bg-zinc-800/30">
                <button
                    onClick={() => setOpen((v) => !v)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] font-mono text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 transition-colors text-left"
                >
                    {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    <span>🔧 {tools.length} tool call{tools.length !== 1 ? 's' : ''}</span>
                    {isStreaming && <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse shrink-0" />}
                    <span className="ml-auto text-zinc-600 text-[10px]">{doneCount}/{tools.length} complete</span>
                </button>
                {open && (
                    <div className="border-t border-zinc-700/40 divide-y divide-zinc-800/60">
                        {tools.map((tool, i) => (
                            <div key={i} className="px-3 py-2">
                                <div className="flex items-center gap-1.5 text-purple-400 text-[11px] font-mono mb-1">
                                    <span>🔧</span>
                                    <span>{tool.name}</span>
                                    {tool.result !== undefined && <span className="text-emerald-500 ml-auto">✓</span>}
                                </div>
                                {tool.args && Object.keys(tool.args).length > 0 && (
                                    <pre className="text-[10px] text-zinc-500 overflow-x-auto whitespace-pre-wrap mb-1">
                                        {JSON.stringify(tool.args, null, 2)}
                                    </pre>
                                )}
                                {tool.result !== undefined && (
                                    <details className="mt-1">
                                        <summary className="text-[10px] text-zinc-600 cursor-pointer select-none list-none">
                                            Result
                                        </summary>
                                        <pre className="mt-1 text-[10px] text-zinc-400 overflow-x-auto max-h-32 whitespace-pre-wrap">
                                            {(() => {
                                                try { return JSON.stringify(JSON.parse(tool.result || ''), null, 2); }
                                                catch { return tool.result; }
                                            })()}
                                        </pre>
                                    </details>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
    code: 'bg-sky-900/60 text-sky-400 border-sky-700/40',
    conversational: 'bg-violet-900/60 text-violet-400 border-violet-700/40',
    orchestrator: 'bg-amber-900/60 text-amber-400 border-amber-700/40',
    builder: 'bg-purple-900/60 text-purple-400 border-purple-700/40',
};

function typeColor(type: string) {
    return TYPE_COLORS[type] ?? 'bg-zinc-800 text-zinc-400 border-zinc-700/40';
}

// ─── Component ────────────────────────────────────────────────────────────────

const BUILDER_WELCOME_MESSAGE: ChatMessage = {
    role: 'assistant',
    content:
        "Hi! I'm the Synapse Builder. Tell me what kind of agent or orchestration you'd like to build, and I'll ask any clarifying questions before creating it.\n\nFor example:\n- *\"Build a research workflow that searches the web and writes a summary to the vault\"*\n- *\"Create an agent that monitors my emails and drafts replies\"*",
    kind: 'text',
};

export function BuilderPanel({
    isOpen,
    onClose,
    agents,
    availableModels,
    currentOrchestrationId,
    onOrchestrationSaved,
    onAgentSaved,
    sessionKey,
}: BuilderPanelProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([BUILDER_WELCOME_MESSAGE]);
    const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
    const [canCreateAgents, setCanCreateAgents] = useState(true);
    const [selectedModel, setSelectedModel] = useState('');
    const [input, setInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
    const [isThinking, setIsThinking] = useState(false);
    const [accordionOpen, setAccordionOpen] = useState(false);

    const bottomRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const toolEntriesRef = useRef<ToolEntry[]>([]);

    // Reset conversation state each time the parent starts a new builder session
    useEffect(() => {
        if (sessionKey === undefined) return;
        setMessages([BUILDER_WELCOME_MESSAGE]);
        setSelectedAgentIds(new Set());
        setCanCreateAgents(true);
        setInput('');
        setAccordionOpen(false);
        toolEntriesRef.current = [];
    }, [sessionKey]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const buildHistory = (msgs: ChatMessage[]) =>
        msgs
            .filter((m) => m.kind === 'text' || m.kind === undefined)
            .map((m) => ({ role: m.role, content: m.content }));

    const toggleAgent = (id: string) => {
        setSelectedAgentIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const sendMessage = async () => {
        const text = input.trim();
        if (!text || streaming) return;

        const userMsg: ChatMessage = { role: 'user', content: text, kind: 'text' };
        const historySnapshot = buildHistory(messages);
        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setStreaming(true);
        setStreamingStatus('Thinking…');
        setIsThinking(true);
        toolEntriesRef.current = [];

        let assistantIdx = -1;

        try {
            const res = await fetch('/api/builder/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    history: historySnapshot,
                    selected_agent_ids: Array.from(selectedAgentIds),
                    can_create_agents: canCreateAgents,
                    model: selectedModel || undefined,
                    current_orchestration_id: currentOrchestrationId,
                }),
            });

            if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

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
                    if (!line.startsWith('data: ')) continue;
                    let event: any;
                    try { event = JSON.parse(line.slice(6)); } catch { continue; }

                    switch (event.type) {
                        case 'thinking':
                            setStreamingStatus('Thinking…');
                            setIsThinking(true);
                            break;

                        case 'chunk':
                            setStreamingStatus(null);
                            setIsThinking(false);
                            if (assistantIdx === -1) {
                                setMessages((prev) => {
                                    assistantIdx = prev.length;
                                    return [...prev, { role: 'assistant', content: event.content, kind: 'text' }];
                                });
                            } else {
                                setMessages((prev) =>
                                    prev.map((m, i) => {
                                        if (i !== assistantIdx) return m;
                                        const base = m.content === '…' ? '' : m.content;
                                        return { ...m, content: base + event.content };
                                    })
                                );
                            }
                            break;

                        case 'tool_call': {
                            const toolName = (event.tool_name as string).replace(/_/g, ' ');
                            toolEntriesRef.current = [
                                ...toolEntriesRef.current,
                                { name: event.tool_name, args: event.args },
                            ];
                            setStreamingStatus(`🔧 ${toolName}…`);
                            setIsThinking(false);
                            break;
                        }

                        case 'tool_result': {
                            const toolName = (event.tool_name as string | undefined)?.replace(/_/g, ' ') ?? 'tool';
                            const entries = [...toolEntriesRef.current];
                            if (entries.length > 0) {
                                entries[entries.length - 1] = { ...entries[entries.length - 1], result: event.result };
                                toolEntriesRef.current = entries;
                            }
                            setStreamingStatus(`✓ ${toolName}`);
                            break;
                        }

                        case 'orchestration_saved':
                            onOrchestrationSaved(event.orchestration as Orchestration);
                            setMessages((prev) => [...prev, {
                                role: 'assistant', kind: 'banner_orch', content: '',
                                bannerText: `✓ Orchestration "${event.orchestration?.name ?? event.orchestration?.id}" saved and loaded into canvas`,
                            }]);
                            break;

                        case 'agent_saved':
                            onAgentSaved(event.agent);
                            setMessages((prev) => [...prev, {
                                role: 'assistant', kind: 'banner_agent', content: '',
                                bannerText: `✓ Agent "${event.agent?.name ?? event.agent?.id}" saved`,
                            }]);
                            break;

                        case 'final':
                            setStreamingStatus(null);
                            setIsThinking(false);
                            setMessages((prev) => {
                                const next = [...prev];
                                if (toolEntriesRef.current.length > 0) {
                                    next.push({
                                        role: 'assistant',
                                        kind: 'tool_group',
                                        content: '',
                                        tools: [...toolEntriesRef.current],
                                    });
                                }
                                next.push({ role: 'assistant', kind: 'text', content: event.response });
                                assistantIdx = next.length - 1;
                                return next;
                            });
                            toolEntriesRef.current = [];
                            break;

                        case 'error':
                            setStreamingStatus(null);
                            setIsThinking(false);
                            setMessages((prev) => {
                                const next = [...prev];
                                if (toolEntriesRef.current.length > 0) {
                                    next.push({ role: 'assistant', kind: 'tool_group', content: '', tools: [...toolEntriesRef.current] });
                                }
                                next.push({ role: 'assistant', kind: 'text', content: `Error: ${event.message}` });
                                assistantIdx = next.length - 1;
                                return next;
                            });
                            toolEntriesRef.current = [];
                            break;
                    }
                }
            }
        } catch (err: any) {
            setMessages((prev) => {
                const next = [...prev];
                if (toolEntriesRef.current.length > 0) {
                    next.push({ role: 'assistant', kind: 'tool_group', content: '', tools: [...toolEntriesRef.current] });
                }
                next.push({ role: 'assistant', kind: 'text', content: `Error: ${err.message}` });
                return next;
            });
            toolEntriesRef.current = [];
        } finally {
            toolEntriesRef.current = [];
            setMessages((prev) => {
                const last = prev[prev.length - 1];
                return last?.kind === 'text' && (last.content === '' || last.content === '…') ? prev.slice(0, -1) : prev;
            });
            setStreaming(false);
            setStreamingStatus(null);
            setIsThinking(false);
            textareaRef.current?.focus();
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    };

    const agentList = agents.filter((a) => a.id !== 'synapse_builder');
    const selectedNames = agentList.filter((a) => selectedAgentIds.has(a.id)).map((a) => a.name);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-y-0 right-0 z-50 w-[620px] bg-zinc-950 border-l border-zinc-800 shadow-2xl flex flex-col">

                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
                    <div className="flex items-center gap-2">
                        <Sparkles size={15} className="text-purple-400" />
                        <span className="text-sm font-semibold text-zinc-100">AI Builder</span>
                    </div>
                    <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
                        <X size={16} />
                    </button>
                </div>

                {/* ── Chat area ───────────────────────────────────────────── */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                    {messages.map((msg, i) => {
                        if (msg.kind === 'tool_group') {
                            const isLast = i === messages.length - 1;
                            return <ToolsCollapsible key={i} tools={msg.tools ?? []} isStreaming={streaming && isLast} />;
                        }

                        if (msg.kind === 'banner_orch' || msg.kind === 'banner_agent') {
                            return (
                                <div key={i} className="flex justify-center">
                                    <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-900/40 border border-emerald-700/50 text-emerald-400 text-xs">
                                        {msg.bannerText}
                                    </div>
                                </div>
                            );
                        }

                        if (msg.role === 'user') {
                            return (
                                <div key={i} className="flex justify-end">
                                    <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-br-sm bg-blue-600 text-white text-sm whitespace-pre-wrap">
                                        {msg.content}
                                    </div>
                                </div>
                            );
                        }

                        return (
                            <div key={i} className="flex justify-start">
                                <div className="max-w-[88%] px-4 py-3 rounded-2xl rounded-bl-sm bg-zinc-800/80 text-zinc-200 text-sm prose prose-invert prose-sm max-w-none">
                                    {msg.content === '…' || msg.content === '' ? (
                                        <span className="flex items-center gap-1.5 text-zinc-500 text-xs">
                                            <Loader2 size={12} className="animate-spin" /> Thinking…
                                        </span>
                                    ) : (
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                    {/* ── Live status indicator ── */}
                    {streaming && (
                        <div className="flex items-center gap-2 pl-1">
                            {isThinking ? (
                                <Loader2 size={11} className="animate-spin text-zinc-500 shrink-0" />
                            ) : (
                                <div className="w-1.5 h-1.5 rounded-full bg-purple-500/70 animate-pulse shrink-0" />
                            )}
                            <span className="text-[11px] text-zinc-500 font-mono">
                                {streamingStatus ?? 'Processing…'}
                            </span>
                        </div>
                    )}

                    <div ref={bottomRef} />
                </div>

                {/* ── Agent accordion (above input) ────────────────────────── */}
                <div className="border-t border-zinc-800 shrink-0">
                    {/* Accordion trigger */}
                    <button
                        className="w-full flex items-center justify-between px-5 py-2.5 hover:bg-zinc-900/60 transition-colors"
                        onClick={() => setAccordionOpen((v) => !v)}
                    >
                        <div className="flex items-center gap-2 min-w-0">
                            <Bot size={13} className="text-zinc-500 shrink-0" />
                            {selectedNames.length === 0 && !canCreateAgents ? (
                                <span className="text-xs text-zinc-500">Select agents to include</span>
                            ) : (
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    {selectedNames.map((n) => (
                                        <span key={n} className="text-[11px] px-2 py-0.5 rounded-full bg-purple-900/50 text-purple-300 border border-purple-700/40">
                                            {n}
                                        </span>
                                    ))}
                                    {canCreateAgents && (
                                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-900/50 text-emerald-400 border border-emerald-700/40 flex items-center gap-1">
                                            <Plus size={9} /> new agents
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>
                        {accordionOpen
                            ? <ChevronDown size={13} className="text-zinc-500 shrink-0 ml-2" />
                            : <ChevronUp size={13} className="text-zinc-500 shrink-0 ml-2" />
                        }
                    </button>

                    {/* Accordion body — opens upward by rendering above the trigger via flex-col-reverse */}
                    {accordionOpen && (
                        <div className="px-4 pb-3 pt-1 max-h-56 overflow-y-auto border-t border-zinc-800/60">
                            {/* Create new agents toggle */}
                            <button
                                onClick={() => setCanCreateAgents((v) => !v)}
                                className={`mb-2 w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border text-left transition-all ${
                                    canCreateAgents
                                        ? 'bg-emerald-900/30 border-emerald-600/60 ring-1 ring-emerald-600/30'
                                        : 'bg-zinc-900 border-zinc-700/60 hover:border-zinc-600 hover:bg-zinc-800/60'
                                }`}
                            >
                                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                                    canCreateAgents ? 'bg-emerald-600 border-emerald-600' : 'border-zinc-600'
                                }`}>
                                    {canCreateAgents && (
                                        <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                                            <path d="M1 3L3 5L7 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                        </svg>
                                    )}
                                </div>
                                <span className="text-xs text-zinc-400">Create new agents if needed</span>
                            </button>

                            {agentList.length === 0 ? (
                                <p className="text-xs text-zinc-600 px-1">No agents configured yet.</p>
                            ) : (
                                <div className="grid grid-cols-2 gap-2">
                                    {agentList.map((agent) => {
                                        const selected = selectedAgentIds.has(agent.id);
                                        return (
                                            <button
                                                key={agent.id}
                                                onClick={() => toggleAgent(agent.id)}
                                                className={`flex items-start gap-2.5 px-3 py-2.5 rounded-lg border text-left transition-all ${
                                                    selected
                                                        ? 'bg-purple-900/30 border-purple-600/60 ring-1 ring-purple-600/30'
                                                        : 'bg-zinc-900 border-zinc-700/60 hover:border-zinc-600 hover:bg-zinc-800/60'
                                                }`}
                                            >
                                                <div className={`mt-0.5 w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                                                    selected ? 'bg-purple-600 border-purple-600' : 'border-zinc-600'
                                                }`}>
                                                    {selected && (
                                                        <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                                                            <path d="M1 3L3 5L7 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                                        </svg>
                                                    )}
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-xs font-medium text-zinc-200 truncate">{agent.name}</p>
                                                    {agent.description ? (
                                                        <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-2 leading-relaxed">{agent.description}</p>
                                                    ) : (
                                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border mt-0.5 inline-block ${typeColor(agent.type || 'conversational')}`}>
                                                            {agent.type || 'conversational'}
                                                        </span>
                                                    )}
                                                </div>
                                            </button>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* ── Input + model (bottom) ───────────────────────────────── */}
                <div className="px-4 pb-4 pt-3 border-t border-zinc-800 shrink-0 space-y-2.5">
                    {/* Textarea row */}
                    <div className="flex items-end gap-2">
                        <textarea
                            ref={textareaRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe what you want to build…"
                            rows={2}
                            disabled={streaming}
                            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-xl px-3.5 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-purple-500/60 resize-none disabled:opacity-50 transition-colors"
                        />
                        <button
                            onClick={sendMessage}
                            disabled={!input.trim() || streaming}
                            className="flex items-center justify-center w-9 h-9 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors shrink-0"
                        >
                            {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                        </button>
                    </div>

                    {/* Model + hint row */}
                    <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-zinc-600 shrink-0">Model</span>
                        <select
                            value={selectedModel}
                            onChange={(e) => setSelectedModel(e.target.value)}
                            className="bg-transparent text-[10px] text-zinc-500 hover:text-zinc-300 outline-none cursor-pointer transition-colors max-w-[160px] truncate"
                        >
                            <option value="" className="bg-zinc-900 text-zinc-300">Default</option>
                            {availableModels.map((m) => (
                                <option key={m} value={m} className="bg-zinc-900 text-zinc-300">{m}</option>
                            ))}
                        </select>
                        <span className="text-[10px] text-zinc-700 ml-auto">Enter to send · Shift+Enter for newline</span>
                    </div>
                </div>
            </div>
    );
}
