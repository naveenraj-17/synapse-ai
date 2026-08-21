"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
/*
 * The overview: what is happening now, what it has cost, and what is in here.
 *
 * Deliberately not a chart-heavy page. Cost, requests, tokens and savings are
 * single headline numbers, so they are stat tiles rather than plots. The one
 * plot is spend by model, which is a magnitude comparison across a handful of
 * named things — a single-series horizontal bar list, so one hue, values
 * direct-labelled, and no legend to decode.
 *
 * Run states reuse the status vocabulary from OrchestrationTab rather than
 * inventing a second one, and every state ships a written label beside its dot
 * so the state never rests on colour alone.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
    Activity, ArrowRight, Bot, Clock, Coins, DollarSign, Hash, Server, Workflow,
} from 'lucide-react';

import { NOTIFICATION_EVENT } from '@/components/notifications/NotificationProvider';

type Run = {
    run_id: string;
    orchestration_id: string;
    status: string;
    started_at: string | null;
    waiting_for_human?: boolean;
};

type ModelStat = { model: string; estimated_cost: number; total_tokens?: number };

type Summary = {
    total_cost: number;
    total_tokens: number;
    total_requests: number;
    total_estimated_savings?: number;
    by_model: ModelStat[];
};

const STATUS: Record<string, { dot: string; text: string; label: string }> = {
    running: { dot: 'bg-blue-400 animate-pulse', text: 'text-blue-300', label: 'Running' },
    paused: { dot: 'bg-yellow-400', text: 'text-yellow-300', label: 'Paused' },
    completed: { dot: 'bg-green-500', text: 'text-zinc-400', label: 'Completed' },
    cancelled: { dot: 'bg-zinc-500', text: 'text-zinc-500', label: 'Cancelled' },
};
const statusOf = (r: Run) =>
    r.status === 'paused' && r.waiting_for_human
        ? { ...STATUS.paused, label: 'Needs input' }
        : STATUS[r.status] ?? { dot: 'bg-red-500', text: 'text-red-300', label: 'Failed' };

const money = (n: number) =>
    n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(2)}`;

const compact = (n: number) =>
    n >= 1e9 ? `${(n / 1e9).toFixed(1)}B`
        : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
            : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K`
                : String(n);

function since(iso: string | null): string {
    if (!iso) return '—';
    const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (secs < 60) return `${Math.floor(secs)}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
    return `${Math.floor(secs / 86400)}d`;
}

/* A headline number. No plot, so no hover layer and no colour to decode —
   the value wears text tokens and the icon carries the identity. */
function Stat({ icon: Icon, label, value, sub }: {
    icon: typeof DollarSign; label: string; value: string; sub?: string;
}) {
    return (
        <div className="rounded-ui border border-border-subtle bg-surface-1 p-4">
            <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wider text-content-muted">
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {label}
            </div>
            <div className="mt-2 text-title font-semibold tabular-nums text-content-primary">{value}</div>
            {sub && <div className="mt-0.5 text-2xs text-content-muted">{sub}</div>}
        </div>
    );
}

function Panel({ title, action, children }: {
    title: string; action?: React.ReactNode; children: React.ReactNode;
}) {
    return (
        <section className="rounded-ui border border-border-subtle bg-surface-1">
            <header className="flex items-center justify-between gap-3 border-b border-border-subtle px-4 py-2.5">
                <h2 className="text-ui font-medium text-content-primary">{title}</h2>
                {action}
            </header>
            <div className="p-4">{children}</div>
        </section>
    );
}

const linkCls = 'text-2xs text-content-muted transition-colors hover:text-content-primary';

export function Dashboard() {
    const router = useRouter();
    const [runs, setRuns] = useState<Run[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [counts, setCounts] = useState({ orchestrations: 0, agents: 0, schedules: 0, schedulesOn: 0, mcp: 0 });
    const [orchNames, setOrchNames] = useState<Record<string, string>>({});
    const [loaded, setLoaded] = useState(false);

    const refreshRuns = useCallback(() => {
        fetch('/api/orchestrations/runs')
            .then(r => r.json())
            .then(d => { if (Array.isArray(d)) setRuns(d); })
            .catch(() => { });
    }, []);

    useEffect(() => {
        refreshRuns();
        const interval = setInterval(refreshRuns, 10000);
        const onVisible = () => { if (document.visibilityState === 'visible') refreshRuns(); };
        document.addEventListener('visibilitychange', onVisible);
        window.addEventListener(NOTIFICATION_EVENT, refreshRuns);
        return () => {
            clearInterval(interval);
            document.removeEventListener('visibilitychange', onVisible);
            window.removeEventListener(NOTIFICATION_EVENT, refreshRuns);
        };
    }, [refreshRuns]);

    useEffect(() => {
        const j = (url: string) => fetch(url).then(r => r.json()).catch(() => null);
        Promise.all([
            j('/api/usage/summary'), j('/api/orchestrations'), j('/api/agents'),
            j('/api/schedules'), j('/api/mcp/servers'),
        ]).then(([usage, orch, agents, schedules, mcp]) => {
            if (usage) setSummary(usage);
            const list = (v: any) => (Array.isArray(v) ? v : Array.isArray(v?.servers) ? v.servers : []);
            const sched = list(schedules);
            setOrchNames(Object.fromEntries(list(orch).map((o: any) => [o.id, o.name])));
            setCounts({
                orchestrations: list(orch).length,
                agents: list(agents).filter((a: any) => !String(a.id ?? '').startsWith('agent_native_builder')).length,
                schedules: sched.length,
                schedulesOn: sched.filter((s: any) => s.enabled !== false).length,
                mcp: list(mcp).length,
            });
            setLoaded(true);
        });
    }, []);

    const live = runs.filter(r => r.status === 'running' || r.status === 'paused');
    const recent = [...runs]
        .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
        .slice(0, 6);

    const models = (summary?.by_model ?? [])
        .slice()
        .sort((a, b) => b.estimated_cost - a.estimated_cost)
        .slice(0, 6);
    const maxCost = Math.max(...models.map(m => m.estimated_cost), 0);

    return (
        <div className="space-y-6">
            {/* ── Happening now ─────────────────────────────────────────── */}
            <Panel
                title="Active now"
                action={live.length > 0
                    ? <Link href="/orchestrations" className={linkCls}>All runs →</Link>
                    : undefined}
            >
                {live.length === 0 ? (
                    <p className="py-2 text-ui text-content-muted">
                        Nothing running. Start an orchestration from{' '}
                        <Link href="/orchestrations" className="text-content-secondary underline underline-offset-2 hover:text-content-primary">
                            Orchestrations
                        </Link>.
                    </p>
                ) : (
                    <ul className="space-y-1">
                        {live.map(run => {
                            const meta = statusOf(run);
                            return (
                                <li key={run.run_id}>
                                    <button
                                        onClick={() => router.push(`/orchestrations?run=${encodeURIComponent(run.run_id)}`)}
                                        className="flex w-full items-center gap-3 rounded-ui px-2 py-2 text-left transition-colors hover:bg-surface-2"
                                    >
                                        <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${meta.dot}`} />
                                        <span className={`w-24 shrink-0 text-2xs ${meta.text}`}>{meta.label}</span>
                                        <span className="min-w-0 flex-1 truncate text-ui text-content-primary">
                                            {orchNames[run.orchestration_id] ?? run.orchestration_id}
                                        </span>
                                        <span className="shrink-0 text-2xs tabular-nums text-content-muted">
                                            {since(run.started_at)}
                                        </span>
                                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-content-muted" aria-hidden />
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Panel>

            {/* ── Headline numbers ──────────────────────────────────────── */}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat icon={DollarSign} label="Total spend" value={summary ? money(summary.total_cost) : '—'} sub="all recorded LLM calls" />
                <Stat icon={Activity} label="Requests" value={summary ? summary.total_requests.toLocaleString() : '—'} />
                <Stat icon={Hash} label="Tokens" value={summary ? compact(summary.total_tokens) : '—'} />
                <Stat icon={Coins} label="Cache saved" value={summary ? money(summary.total_estimated_savings ?? 0) : '—'} sub="vs uncached pricing" />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
                {/* ── Spend by model ─────────────────────────────────────
                    One series, so one hue and no legend: the row label is the
                    identity and the value is direct-labelled beside it. */}
                <Panel title="Spend by model" action={<Link href="/usage" className={linkCls}>Usage →</Link>}>
                    {models.length === 0 ? (
                        <p className="py-2 text-ui text-content-muted">No usage recorded yet.</p>
                    ) : (
                        <ul className="space-y-3">
                            {models.map(m => (
                                <li key={m.model} title={`${m.model} — ${money(m.estimated_cost)}`}>
                                    <div className="mb-1.5 flex items-baseline justify-between gap-3">
                                        <span className="min-w-0 truncate text-ui text-content-secondary">{m.model}</span>
                                        <span className="shrink-0 text-ui tabular-nums text-content-primary">
                                            {money(m.estimated_cost)}
                                        </span>
                                    </div>
                                    <div className="h-2 w-full rounded-[4px] bg-surface-2">
                                        <div
                                            className="h-2 rounded-r-[4px] bg-emerald-500"
                                            style={{ width: `${maxCost > 0 ? Math.max(2, (m.estimated_cost / maxCost) * 100) : 0}%` }}
                                        />
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </Panel>

                {/* ── What is in the workspace ───────────────────────────── */}
                <Panel title="Workspace">
                    <ul className="divide-y divide-border-subtle">
                        {[
                            { icon: Workflow, label: 'Orchestrations', href: '/orchestrations', value: counts.orchestrations },
                            { icon: Bot, label: 'Agents', href: '/agents', value: counts.agents },
                            {
                                icon: Clock, label: 'Schedules', href: '/schedules', value: counts.schedules,
                                sub: counts.schedules > 0 ? `${counts.schedulesOn} enabled` : undefined,
                            },
                            { icon: Server, label: 'MCP servers', href: '/mcp-servers', value: counts.mcp },
                        ].map(row => (
                            <li key={row.href}>
                                <Link href={row.href} className="flex items-center gap-3 py-2.5 transition-colors hover:text-content-primary">
                                    <row.icon className="h-4 w-4 shrink-0 text-content-muted" aria-hidden />
                                    <span className="flex-1 text-ui text-content-secondary">{row.label}</span>
                                    {row.sub && <span className="text-2xs text-content-muted">{row.sub}</span>}
                                    <span className="w-10 text-right text-ui tabular-nums text-content-primary">
                                        {loaded ? row.value : '—'}
                                    </span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                </Panel>
            </div>

            {/* ── Recent runs ───────────────────────────────────────────── */}
            <Panel title="Recent runs" action={<Link href="/runs" className={linkCls}>Runs &amp; Logs →</Link>}>
                {recent.length === 0 ? (
                    <p className="py-2 text-ui text-content-muted">No runs yet.</p>
                ) : (
                    <ul className="divide-y divide-border-subtle">
                        {recent.map(run => {
                            const meta = statusOf(run);
                            return (
                                <li key={run.run_id}>
                                    <button
                                        onClick={() => router.push(`/orchestrations?run=${encodeURIComponent(run.run_id)}`)}
                                        className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:text-content-primary"
                                    >
                                        <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${meta.dot}`} />
                                        <span className={`w-24 shrink-0 text-2xs ${meta.text}`}>{meta.label}</span>
                                        <span className="min-w-0 flex-1 truncate text-ui text-content-secondary">
                                            {orchNames[run.orchestration_id] ?? run.orchestration_id}
                                        </span>
                                        <span className="shrink-0 text-2xs tabular-nums text-content-muted">
                                            {since(run.started_at)} ago
                                        </span>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Panel>
        </div>
    );
}
