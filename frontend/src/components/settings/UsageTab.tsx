'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
    DollarSign, TrendingUp, Zap, BarChart3, RefreshCw, Trash2,
    ChevronDown, ChevronUp, Clock, Activity, Cpu,
    AlertTriangle, CheckCircle2, Info, Plus, Save, X, Edit2, Check
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────
interface UsageSummary {
    total_cost: number;
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    total_requests: number;
    by_model: ModelStat[];
    by_session: SessionStat[];
}
interface ModelStat {
    model: string; provider: string; requests: number;
    input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost: number;
}
interface SessionStat {
    session_id: string; agent_id: string; requests: number;
    input_tokens: number; output_tokens: number; total_tokens: number;
    context_chars: number; estimated_cost: number; models_used: string[];
    first_ts: string; last_ts: string; source: string;
}
interface UsageLog {
    timestamp: string; model: string; provider: string;
    session_id: string; agent_id: string; source: string; run_id?: string;
    input_tokens: number; output_tokens: number; total_tokens: number;
    context_chars: number; estimated_cost: number; latency_seconds: number;
}
interface PricingEntry {
    provider: string; input_per_1m: number; output_per_1m: number;
}

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────
const PROVIDERS = ['openai', 'anthropic', 'gemini', 'grok', 'deepseek', 'bedrock', 'ollama'] as const;
type Provider = typeof PROVIDERS[number];

const PROVIDER_META: Record<Provider, { label: string; color: string; dot: string; bg: string; text: string }> = {
    openai:    { label: 'OpenAI',        color: '#10b981', dot: '#10b981', bg: 'bg-emerald-950/60', text: 'text-emerald-400' },
    anthropic: { label: 'Anthropic',     color: '#f59e0b', dot: '#f59e0b', bg: 'bg-amber-950/60',   text: 'text-amber-400' },
    gemini:    { label: 'Gemini',        color: '#3b82f6', dot: '#3b82f6', bg: 'bg-blue-950/60',    text: 'text-blue-400' },
    grok:      { label: 'xAI Grok',      color: '#a1a1aa', dot: '#a1a1aa', bg: 'bg-zinc-800/60',    text: 'text-zinc-300' },
    deepseek:  { label: 'DeepSeek',      color: '#8b5cf6', dot: '#8b5cf6', bg: 'bg-violet-950/60',  text: 'text-violet-400' },
    bedrock:   { label: 'AWS Bedrock',   color: '#f97316', dot: '#f97316', bg: 'bg-orange-950/60',  text: 'text-orange-400' },
    ollama:    { label: 'Ollama (Local)', color: '#94a3b8', dot: '#94a3b8', bg: 'bg-slate-800/60',   text: 'text-slate-400' },
};

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
function fmt$(n: number) {
    if (n === 0) return '$0.00';
    if (n < 0.000001) return '<$0.000001';
    if (n < 0.01) return `$${n.toFixed(6)}`;
    return `$${n.toFixed(4)}`;
}
function fmtK(n: number) {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
}
function fmtKB(chars: number) {
    const kb = chars / 1024;
    return kb >= 1 ? `${kb.toFixed(1)}KB` : `${chars}B`;
}
function fmtDate(ts: string) {
    if (!ts) return '—';
    try {
        return new Date(ts).toLocaleString(undefined, {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
        });
    } catch { return ts; }
}
function fmtTime(ts: string) {
    if (!ts) return '—';
    try {
        return new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ts; }
}
function detectProvider(model: string): Provider {
    if (model.startsWith('gpt') || model.startsWith('o1') || model.startsWith('o3') || model.startsWith('o4')) return 'openai';
    if (model.startsWith('claude')) return 'anthropic';
    if (model.startsWith('gemini')) return 'gemini';
    if (model.startsWith('grok')) return 'grok';
    if (model.startsWith('deepseek')) return 'deepseek';
    if (model.startsWith('anthropic.') || model.startsWith('amazon.') || model.startsWith('meta.') || model.startsWith('mistral.')) return 'bedrock';
    return 'ollama';
}

// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────
function ProviderBadge({ provider }: { provider: string }) {
    const meta = PROVIDER_META[provider as Provider] ?? PROVIDER_META.ollama;
    return (
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium ${meta.bg} ${meta.text} border border-white/5`}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.dot }} />
            {provider || 'local'}
        </span>
    );
}

function StatCard({ icon: Icon, label, value, sub, color }: {
    icon: any; label: string; value: string; sub?: string; color: string;
}) {
    return (
        <div className="relative flex flex-col gap-3 p-5 bg-zinc-900/80 border border-white/5 overflow-hidden group hover:border-white/10 transition-all duration-300">
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                style={{ background: `radial-gradient(ellipse at top left, ${color}10 0%, transparent 70%)` }} />
            <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 font-medium tracking-wider uppercase">{label}</span>
                <div className="p-2" style={{ background: `${color}18` }}>
                    <Icon className="w-4 h-4" style={{ color }} />
                </div>
            </div>
            <div>
                <p className="text-2xl font-bold tracking-tight text-white">{value}</p>
                {sub && <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>}
            </div>
        </div>
    );
}

function ModelBar({ stat, maxCost }: { stat: ModelStat; maxCost: number }) {
    const pct = maxCost > 0 ? (stat.estimated_cost / maxCost) * 100 : 0;
    const meta = PROVIDER_META[detectProvider(stat.model)] ?? PROVIDER_META.ollama;
    return (
        <div className="flex items-center gap-4 py-3 border-b border-white/5 last:border-0 -mx-4 px-4 hover:bg-white/2 transition-colors">
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-sm font-medium text-white truncate">{stat.model}</span>
                    <ProviderBadge provider={stat.provider} />
                </div>
                <div className="h-1 bg-zinc-800 overflow-hidden">
                    <div className="h-full transition-all duration-700" style={{ width: `${pct}%`, background: meta.dot }} />
                </div>
            </div>
            <div className="flex gap-6 text-right shrink-0">
                <div><p className="text-xs text-zinc-500">Reqs</p><p className="text-sm font-semibold text-white">{stat.requests}</p></div>
                <div><p className="text-xs text-zinc-500">Tokens</p><p className="text-sm font-semibold text-white">{fmtK(stat.total_tokens)}</p></div>
                <div className="min-w-[70px]"><p className="text-xs text-zinc-500">Cost</p>
                    <p className="text-sm font-semibold" style={{ color: meta.dot }}>{fmt$(stat.estimated_cost)}</p></div>
            </div>
        </div>
    );
}

// Per-session drill-down with per-call context delta
function SessionRow({ s }: { s: SessionStat }) {
    const [open, setOpen] = useState(false);
    const [logs, setLogs] = useState<UsageLog[]>([]);
    const [loadingLogs, setLoadingLogs] = useState(false);
    const isOrch = s.source === 'orchestration';

    const loadLogs = useCallback(async () => {
        if (logs.length > 0) return;
        setLoadingLogs(true);
        try {
            const res = await fetch(`/api/usage/logs?session_id=${encodeURIComponent(s.session_id)}&limit=200`);
            const data = await res.json();
            setLogs(data.logs ?? []);
        } catch { /* silently ignore */ }
        finally { setLoadingLogs(false); }
    }, [s.session_id, logs.length]);

    const toggle = () => {
        if (!open) loadLogs();
        setOpen(o => !o);
    };

    return (
        <div className="border border-white/5 mb-2 hover:border-white/10 transition-colors overflow-hidden">
            <button onClick={toggle}
                className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-white/3 transition-colors">
                <div className="flex items-center gap-2 shrink-0">
                    {isOrch
                        ? <Activity className="w-3.5 h-3.5 text-violet-400" />
                        : <Zap className="w-3.5 h-3.5 text-emerald-400" />}
                    <span className={`text-xs px-2 py-0.5 font-medium border ${isOrch ? 'border-violet-800/50 text-violet-400 bg-violet-950/40' : 'border-emerald-800/50 text-emerald-400 bg-emerald-950/40'}`}>
                        {isOrch ? 'orch' : 'chat'}
                    </span>
                </div>
                <span className="flex-1 text-xs text-zinc-400 font-mono truncate">{s.session_id}</span>
                <div className="flex items-center gap-5 text-right shrink-0 text-sm">
                    <div className="hidden md:block"><p className="text-xs text-zinc-500">Turns</p><p className="font-semibold text-white">{s.requests}</p></div>
                    <div className="hidden lg:block"><p className="text-xs text-zinc-500">Context</p><p className="font-semibold text-white">{fmtKB(s.context_chars)}</p></div>
                    <div><p className="text-xs text-zinc-500">Tokens</p><p className="font-semibold text-white">{fmtK(s.total_tokens)}</p></div>
                    <div className="min-w-[70px]"><p className="text-xs text-zinc-500">Cost</p>
                        <p className="font-semibold text-emerald-400">{fmt$(s.estimated_cost)}</p></div>
                </div>
                {open ? <ChevronUp className="w-4 h-4 text-zinc-500 shrink-0" /> : <ChevronDown className="w-4 h-4 text-zinc-500 shrink-0" />}
            </button>

            {open && (
                <div className="border-t border-white/5 bg-zinc-950/50">
                    {/* Session metadata */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-4 py-3 border-b border-white/5 text-xs">
                        <div><p className="text-zinc-500 mb-1">Agent</p><p className="text-zinc-300 font-mono truncate">{s.agent_id}</p></div>
                        <div><p className="text-zinc-500 mb-1">Models</p>
                            <div className="flex flex-wrap gap-1">
                                {s.models_used.map(m => <span key={m} className="bg-zinc-800 text-zinc-300 px-1.5 py-0.5 text-xs truncate max-w-[100px]">{m}</span>)}
                            </div>
                        </div>
                        <div><p className="text-zinc-500 mb-1">In / Out</p><p className="text-zinc-300">{fmtK(s.input_tokens)} / {fmtK(s.output_tokens)}</p></div>
                        <div><p className="text-zinc-500 mb-1">Last Active</p><p className="text-zinc-300">{fmtDate(s.last_ts)}</p></div>
                    </div>

                    {/* Per-turn context breakdown */}
                    <div className="px-4 py-3">
                        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Per-Turn Breakdown</p>
                        {loadingLogs && (
                            <div className="flex items-center gap-2 py-4 text-zinc-600 text-xs">
                                <RefreshCw className="w-3 h-3 animate-spin" /> Loading turns...
                            </div>
                        )}
                        {!loadingLogs && logs.length === 0 && (
                            <p className="text-zinc-600 text-xs py-3">No detailed logs found for this session.</p>
                        )}
                        {!loadingLogs && logs.length > 0 && (
                            <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="border-b border-white/5">
                                            <th className="text-left pb-2 text-zinc-500 font-medium pr-4">#</th>
                                            <th className="text-left pb-2 text-zinc-500 font-medium pr-4">Time</th>
                                            <th className="text-left pb-2 text-zinc-500 font-medium pr-4">Model</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium pr-4">Context</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium pr-4">Δ Context</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium pr-4">In</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium pr-4">Out</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium pr-4">Latency</th>
                                            <th className="text-right pb-2 text-zinc-500 font-medium">Cost</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {logs.map((log, i) => {
                                            const prevCtx = i > 0 ? logs[i - 1].context_chars : 0;
                                            const delta = log.context_chars - prevCtx;
                                            const metaDot = PROVIDER_META[detectProvider(log.model)]?.dot ?? '#71717a';
                                            return (
                                                <tr key={i} className="border-b border-white/3 last:border-0 hover:bg-white/2">
                                                    <td className="py-2 pr-4 text-zinc-600">{i + 1}</td>
                                                    <td className="py-2 pr-4 text-zinc-500 whitespace-nowrap">{fmtTime(log.timestamp)}</td>
                                                    <td className="py-2 pr-4 text-zinc-300 font-mono max-w-[140px] truncate">{log.model}</td>
                                                    <td className="py-2 pr-4 text-right text-zinc-300">{fmtKB(log.context_chars)}</td>
                                                    <td className="py-2 pr-4 text-right">
                                                        <span className={delta > 0 ? 'text-amber-400' : 'text-zinc-600'}>
                                                            {delta > 0 ? `+${fmtKB(delta)}` : '—'}
                                                        </span>
                                                    </td>
                                                    <td className="py-2 pr-4 text-right text-zinc-400">{fmtK(log.input_tokens)}</td>
                                                    <td className="py-2 pr-4 text-right text-zinc-400">{fmtK(log.output_tokens)}</td>
                                                    <td className="py-2 pr-4 text-right text-zinc-500">{log.latency_seconds.toFixed(1)}s</td>
                                                    <td className="py-2 text-right font-medium" style={{ color: metaDot }}>{fmt$(log.estimated_cost)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Editable Pricing Table
// ─────────────────────────────────────────────────────────────
type EditablePricing = Record<string, PricingEntry & { _editing?: boolean; _new?: boolean }>;

function PricingEditor({ initialPricing, onSaved }: {
    initialPricing: Record<string, PricingEntry>;
    onSaved: (p: Record<string, PricingEntry>) => void;
}) {
    const [pricing, setPricing] = useState<EditablePricing>(() => JSON.parse(JSON.stringify(initialPricing)));
    const [activeProvider, setActiveProvider] = useState<Provider | 'all'>('all');
    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState<string | null>(null);
    const [dirty, setDirty] = useState(false);

    // New model form state
    const [addingFor, setAddingFor] = useState<Provider | null>(null);
    const [newModel, setNewModel] = useState('');
    const [newIn, setNewIn] = useState('');
    const [newOut, setNewOut] = useState('');

    // Update a field
    const update = (model: string, field: 'input_per_1m' | 'output_per_1m', val: string) => {
        const num = parseFloat(val);
        if (isNaN(num) || num < 0) return;
        setPricing(p => ({ ...p, [model]: { ...p[model], [field]: num } }));
        setDirty(true);
    };

    const removeModel = (model: string) => {
        setPricing(p => { const c = { ...p }; delete c[model]; return c; });
        setDirty(true);
    };

    const addModel = (provider: Provider) => {
        if (!newModel.trim()) return;
        const key = newModel.trim();
        const inp = parseFloat(newIn) || 0;
        const out = parseFloat(newOut) || 0;
        setPricing(p => ({ ...p, [key]: { provider, input_per_1m: inp, output_per_1m: out, _new: true } }));
        setNewModel(''); setNewIn(''); setNewOut('');
        setAddingFor(null);
        setDirty(true);
    };

    const save = async () => {
        setSaving(true);
        setSaveMsg(null);
        try {
            // Strip internal UI flags
            const clean: Record<string, PricingEntry> = {};
            for (const [k, v] of Object.entries(pricing)) {
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                const { _editing, _new, ...rest } = v as any;
                clean[k] = rest;
            }
            const res = await fetch('/api/usage/pricing', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(clean),
            });
            if (!res.ok) throw new Error(`Server error ${res.status}`);
            setSaveMsg('Saved!');
            setDirty(false);
            onSaved(clean);
            setTimeout(() => setSaveMsg(null), 2000);
        } catch (e: any) {
            setSaveMsg(`Error: ${e.message}`);
        } finally {
            setSaving(false);
        }
    };

    const providerModels = (provider: Provider | 'all') =>
        Object.entries(pricing).filter(([, v]) => provider === 'all' || v.provider === provider);

    const providerList = PROVIDERS.filter(p => p !== 'ollama' || Object.values(pricing).some(v => v.provider === 'ollama'));

    return (
        <div className="border border-white/5">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/5 bg-zinc-900/40">
                <div className="flex items-center gap-3">
                    <Info className="w-4 h-4 text-zinc-400" />
                    <span className="text-sm font-semibold text-white">Pricing Reference</span>
                    <span className="text-xs text-zinc-500">— edit rates used for cost calculation (USD / 1M tokens)</span>
                </div>
                <div className="flex items-center gap-3">
                    {saveMsg && (
                        <span className={`text-xs ${saveMsg.startsWith('Error') ? 'text-red-400' : 'text-emerald-400'}`}>
                            {saveMsg}
                        </span>
                    )}
                    {dirty && (
                        <button onClick={save} disabled={saving}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-white text-black font-semibold hover:bg-zinc-200 transition-colors disabled:opacity-50">
                            {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                            Save Pricing
                        </button>
                    )}
                </div>
            </div>

            {/* Provider tabs */}
            <div className="flex items-center gap-0 border-b border-white/5 overflow-x-auto">
                {(['all', ...providerList] as (typeof providerList[number] | 'all')[]).map(p => {
                    const isActive = activeProvider === p;
                    const meta = p === 'all' ? null : PROVIDER_META[p];
                    return (
                        <button key={p} onClick={() => setActiveProvider(p)}
                            className={`px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${isActive
                                ? 'border-white text-white'
                                : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
                            {meta ? (
                                <span className="flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.dot }} />
                                    {meta.label}
                                </span>
                            ) : 'All Providers'}
                        </button>
                    );
                })}
            </div>

            {/* Model rows */}
            <div>
                {(activeProvider === 'all' ? providerList : [activeProvider]).map(provider => {
                    const models = providerModels(provider);
                    if (models.length === 0 && addingFor !== provider) return null;
                    const meta = PROVIDER_META[provider];
                    return (
                        <div key={provider} className="border-b border-white/5 last:border-0">
                            {/* Provider header row */}
                            <div className={`flex items-center justify-between px-5 py-2 ${meta.bg}`}>
                                <div className="flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.dot }} />
                                    <span className={`text-xs font-semibold uppercase tracking-wider ${meta.text}`}>{meta.label}</span>
                                    <span className="text-xs text-zinc-600">({models.length} models)</span>
                                </div>
                                <button onClick={() => setAddingFor(addingFor === provider ? null : provider)}
                                    className="flex items-center gap-1 text-xs text-zinc-500 hover:text-white transition-colors">
                                    <Plus className="w-3 h-3" /> Add model
                                </button>
                            </div>

                            {/* Column headers */}
                            {models.length > 0 && (
                                <div className="grid grid-cols-[1fr_130px_130px_36px] gap-2 px-5 py-1.5 text-xs text-zinc-600 border-b border-white/3">
                                    <span>Model ID</span>
                                    <span className="text-right">Input / 1M tokens</span>
                                    <span className="text-right">Output / 1M tokens</span>
                                    <span />
                                </div>
                            )}

                            {/* Model rows */}
                            {models.map(([model, entry]) => (
                                <div key={model} className="grid grid-cols-[1fr_130px_130px_36px] gap-2 items-center px-5 py-2.5 border-b border-white/3 last:border-0 hover:bg-white/2 transition-colors">
                                    <span className="text-xs font-mono text-zinc-300 truncate pr-2">
                                        {model}
                                        {(entry as any)._new && <span className="ml-2 text-emerald-500 text-[10px]">NEW</span>}
                                    </span>
                                    <div className="flex items-center gap-1 justify-end">
                                        <span className="text-zinc-500 text-xs">$</span>
                                        <input
                                            type="number" min="0" step="0.001"
                                            value={entry.input_per_1m}
                                            onChange={e => update(model, 'input_per_1m', e.target.value)}
                                            className="w-20 bg-zinc-800 border border-white/10 text-white text-xs px-2 py-1 text-right focus:outline-none focus:border-white/30 transition-colors"
                                        />
                                    </div>
                                    <div className="flex items-center gap-1 justify-end">
                                        <span className="text-zinc-500 text-xs">$</span>
                                        <input
                                            type="number" min="0" step="0.001"
                                            value={entry.output_per_1m}
                                            onChange={e => update(model, 'output_per_1m', e.target.value)}
                                            className="w-20 bg-zinc-800 border border-white/10 text-white text-xs px-2 py-1 text-right focus:outline-none focus:border-white/30 transition-colors"
                                        />
                                    </div>
                                    <button onClick={() => removeModel(model)}
                                        className="text-zinc-600 hover:text-red-400 transition-colors flex items-center justify-center">
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            ))}

                            {/* Add model form */}
                            {addingFor === provider && (
                                <div className="grid grid-cols-[1fr_130px_130px_36px] gap-2 items-center px-5 py-3 bg-zinc-900/80 border-t border-white/5">
                                    <input
                                        placeholder="model-id (e.g. anthropic.claude-3-5...)"
                                        value={newModel}
                                        onChange={e => setNewModel(e.target.value)}
                                        className="bg-zinc-800 border border-white/20 text-white text-xs px-2 py-1.5 focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-600"
                                    />
                                    <div className="flex items-center gap-1 justify-end">
                                        <span className="text-zinc-500 text-xs">$</span>
                                        <input placeholder="0.000" value={newIn} onChange={e => setNewIn(e.target.value)}
                                            type="number" min="0" step="0.001"
                                            className="w-20 bg-zinc-800 border border-white/20 text-white text-xs px-2 py-1.5 text-right focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-600"
                                        />
                                    </div>
                                    <div className="flex items-center gap-1 justify-end">
                                        <span className="text-zinc-500 text-xs">$</span>
                                        <input placeholder="0.000" value={newOut} onChange={e => setNewOut(e.target.value)}
                                            type="number" min="0" step="0.001"
                                            className="w-20 bg-zinc-800 border border-white/20 text-white text-xs px-2 py-1.5 text-right focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-600"
                                        />
                                    </div>
                                    <button onClick={() => addModel(provider)}
                                        className="text-emerald-400 hover:text-emerald-300 transition-colors flex items-center justify-center">
                                        <Check className="w-4 h-4" />
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────
export function UsageTab() {
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [pricing, setPricing] = useState<Record<string, PricingEntry>>({});
    const [loading, setLoading] = useState(true);
    const [clearing, setClearing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [sessionPage, setSessionPage] = useState(0);
    const PAGE_SIZE = 20;

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [sumRes, priceRes] = await Promise.all([
                fetch('/api/usage/summary'),
                fetch('/api/usage/pricing'),
            ]);
            if (!sumRes.ok) throw new Error(`Summary fetch failed: ${sumRes.status}`);
            if (!priceRes.ok) throw new Error(`Pricing fetch failed: ${priceRes.status}`);
            const [sumData, priceData] = await Promise.all([sumRes.json(), priceRes.json()]);
            setSummary(sumData);
            setPricing(priceData);
        } catch (e: any) {
            setError(e.message || 'Failed to load usage data');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleClear = async () => {
        if (!confirm('Delete all usage logs? This cannot be undone.')) return;
        setClearing(true);
        try {
            await fetch('/api/usage/logs', { method: 'DELETE' });
            await load();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setClearing(false);
        }
    };

    const sessions = summary?.by_session ?? [];
    const pagedSessions = sessions.slice(sessionPage * PAGE_SIZE, (sessionPage + 1) * PAGE_SIZE);
    const maxModelCost = Math.max(...(summary?.by_model.map(m => m.estimated_cost) ?? [0]));

    return (
        <div className="flex-1 overflow-y-auto bg-black text-white font-mono modern-scrollbar">
            {/* Header */}
            <div className="sticky top-0 z-10 border-b border-white/5 bg-black/90 backdrop-blur-sm px-6 md:px-10 py-4">
                <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
                    <div>
                        <h1 className="text-lg font-bold tracking-wider flex items-center gap-2">
                            <DollarSign className="w-5 h-5 text-emerald-400" />
                            USAGE & COSTS
                        </h1>
                        <p className="text-xs text-zinc-500 mt-0.5">Token usage and cost tracking across all LLM calls</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button onClick={load} disabled={loading}
                            className="flex items-center gap-2 px-3 py-2 text-xs border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 transition-all">
                            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                            Refresh
                        </button>
                        <button onClick={handleClear} disabled={clearing || loading}
                            className="flex items-center gap-2 px-3 py-2 text-xs border border-red-900/50 text-red-400 hover:border-red-700 hover:text-red-300 transition-all">
                            <Trash2 className="w-3.5 h-3.5" />
                            Clear Logs
                        </button>
                    </div>
                </div>
            </div>

            <div className="max-w-6xl mx-auto px-6 md:px-10 py-8 space-y-8">

                {error && (
                    <div className="flex items-center gap-3 p-4 bg-red-950/40 border border-red-800/40 text-red-300 text-sm">
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                {loading && !summary && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="h-28 bg-zinc-900/80 border border-white/5 animate-pulse" />
                        ))}
                    </div>
                )}

                {!loading && summary && summary.total_requests === 0 && (
                    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
                        <div className="p-4 bg-zinc-900 border border-white/5">
                            <BarChart3 className="w-8 h-8 text-zinc-600" />
                        </div>
                        <div>
                            <p className="text-zinc-400 font-medium">No usage data yet</p>
                            <p className="text-zinc-600 text-sm mt-1">Send a chat message to start tracking costs</p>
                        </div>
                    </div>
                )}

                {summary && summary.total_requests > 0 && (
                    <>
                        {/* Summary Cards */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={DollarSign} label="Total Cost" value={fmt$(summary.total_cost)} sub="estimated USD" color="#10b981" />
                            <StatCard icon={TrendingUp} label="Total Requests" value={summary.total_requests.toLocaleString()} sub="LLM calls" color="#3b82f6" />
                            <StatCard icon={Zap} label="Input Tokens" value={fmtK(summary.total_input_tokens)} sub="prompt tokens" color="#f59e0b" />
                            <StatCard icon={Cpu} label="Output Tokens" value={fmtK(summary.total_output_tokens)} sub="completion tokens" color="#8b5cf6" />
                        </div>

                        {/* Cost by Model */}
                        <div className="bg-zinc-900/60 border border-white/5 p-5">
                            <div className="flex items-center gap-2 mb-5">
                                <BarChart3 className="w-4 h-4 text-zinc-400" />
                                <h2 className="text-sm font-semibold text-white tracking-wide">Cost by Model</h2>
                                <span className="text-xs text-zinc-600">sorted by spend</span>
                            </div>
                            {summary.by_model.map(stat => (
                                <ModelBar key={stat.model} stat={stat} maxCost={maxModelCost} />
                            ))}
                        </div>

                        {/* Session History */}
                        <div className="bg-zinc-900/60 border border-white/5 p-5">
                            <div className="flex items-center justify-between mb-5">
                                <div className="flex items-center gap-2">
                                    <Clock className="w-4 h-4 text-zinc-400" />
                                    <h2 className="text-sm font-semibold text-white tracking-wide">Session History</h2>
                                    <span className="text-xs text-zinc-600">{sessions.length} sessions — click to expand per-turn breakdown</span>
                                </div>
                                <div className="flex items-center gap-3 text-xs text-zinc-500">
                                    <span className="flex items-center gap-1.5"><Zap className="w-3 h-3 text-emerald-400" /> Chat</span>
                                    <span className="flex items-center gap-1.5"><Activity className="w-3 h-3 text-violet-400" /> Orchestration</span>
                                </div>
                            </div>

                            {pagedSessions.map(s => <SessionRow key={s.session_id} s={s} />)}

                            {sessions.length > PAGE_SIZE && (
                                <div className="flex items-center justify-between mt-4 pt-4 border-t border-white/5">
                                    <button onClick={() => setSessionPage(p => Math.max(0, p - 1))}
                                        disabled={sessionPage === 0}
                                        className="px-3 py-1.5 text-xs border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                                        ← Previous
                                    </button>
                                    <span className="text-xs text-zinc-500">Page {sessionPage + 1} of {Math.ceil(sessions.length / PAGE_SIZE)}</span>
                                    <button onClick={() => setSessionPage(p => p + 1)}
                                        disabled={(sessionPage + 1) * PAGE_SIZE >= sessions.length}
                                        className="px-3 py-1.5 text-xs border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                                        Next →
                                    </button>
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* Editable Pricing Table — always visible */}
                {Object.keys(pricing).length > 0 && (
                    <PricingEditor initialPricing={pricing} onSaved={setPricing} />
                )}

                {/* Disclaimer */}
                <div className="flex items-start gap-3 p-4 bg-zinc-900/40 border border-white/5 text-xs text-zinc-500">
                    <CheckCircle2 className="w-4 h-4 text-zinc-600 shrink-0 mt-0.5" />
                    <div>
                        <p className="font-medium text-zinc-400 mb-1">About cost estimates</p>
                        <p>
                            Token counts come from API response metadata (OpenAI, Anthropic, Gemini, Grok, DeepSeek)
                            or Ollama&#39;s eval_count. Bedrock uses a character-count heuristic (chars ÷ 4).
                            Edit prices above and click <strong>Save Pricing</strong> to update rates used for all future cost calculations.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
