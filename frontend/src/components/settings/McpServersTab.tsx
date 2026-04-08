/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from 'react';
import {
    Server, Plus, Trash, RefreshCw, Loader2,
    CheckCircle, XCircle, AlertCircle, Zap,
    Terminal, Globe, Eye, EyeOff
} from 'lucide-react';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '@/store';
import { setMcpServers, updateMcpServerStatus } from '@/store/settingsSlice';

// ── Types ──────────────────────────────────────────────────────────────────────

interface McpToast {
    show: boolean;
    message: string;
    type: 'success' | 'warning' | 'error';
}

type DraftServer = {
    name: string;
    label: string;
    server_type: 'stdio' | 'remote';
    command: string;
    args: string;
    env: { key: string; value: string }[];
    url: string;
    token: string;
};

interface McpServersTabProps {
    mcpServers: any[];
    loadingMcp: boolean;
    isConnecting: boolean;
    lastConnected: boolean | null;
    mcpToast: McpToast | null;
    setMcpToast: (t: McpToast | null) => void;
    pendingServerName: string | null;      // remote server awaiting OAuth
    onPendingResolved: () => void;         // call when connected or timed-out
    draftMcpServer: DraftServer;
    setDraftMcpServer: (v: DraftServer) => void;
    onAddServer: () => void;
    onDeleteServer: (name: string) => void;
    onReconnectServer: (name: string) => void;
}

// ── Presets ────────────────────────────────────────────────────────────────────

interface Preset {
    name: string;
    server_type: 'stdio' | 'remote';
    label: string;
    // stdio
    command?: string;
    args?: string;
    env?: Record<string, string>;
    // remote
    url?: string;
    token?: string;
}

const STDIO_PRESETS: Preset[] = [
    { server_type: 'stdio', name: 'Git', command: 'uvx', args: 'mcp-server-git', label: 'Git' }
];

const REMOTE_PRESETS: Preset[] = [
    { server_type: 'remote', name: 'Vercel', url: 'https://mcp.vercel.com', label: 'Vercel' },
    { server_type: 'remote', name: 'Github', url: 'https://api.githubcopilot.com/mcp/', label: 'GitHub Copilot', token: 'GITHUB_PERSONAL_ACCESS_TOKEN' },
    { server_type: 'remote', name: 'slack', url: 'https://mcp.slack.com/mcp', label: 'Slack', token: 'SLACK_CLIENT_ID' },
    { server_type: 'remote', name: 'notion', url: 'https://mcp.notion.com/mcp', label: 'Notion' },
    { server_type: 'remote', name: 'Jira', url: 'https://mcp.atlassian.com/v1/mcp', label: 'Jira' },
    { server_type: 'remote', name: 'Zapier', url: 'https://mcp.zapier.com/api/mcp/mcp', label: 'Zapier' },
    { server_type: 'remote', name: 'Figma', url: 'https://mcp.figma.com/mcp', label: 'Figma', token: 'FIGMA_PERSONAL_ACCESS_TOKEN' },
    { server_type: 'remote', name: 'Fetch', url: 'https://remote.mcpservers.org/fetch/mcp', label: 'Fetch' },
];

// ── Sub-components ─────────────────────────────────────────────────────────────

const StatusBadge = ({ status }: { status?: string }) => {
    if (status === 'connecting') return (
        <span className="flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30 uppercase">
            <Loader2 className="h-2.5 w-2.5 animate-spin" /> Connecting
        </span>
    );
    if (status === 'connected') return (
        <span className="flex items-center gap-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30 uppercase">
            <CheckCircle className="h-2.5 w-2.5" /> Active
        </span>
    );
    return (
        <span className="flex items-center gap-1 text-[10px] bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded border border-yellow-500/30 uppercase">
            <XCircle className="h-2.5 w-2.5" /> Disconnected
        </span>
    );
};

const TypePill = ({ type }: { type?: string }) => (
    type === 'remote'
        ? <span className="flex items-center gap-1 text-[9px] bg-violet-500/15 text-violet-400 px-1.5 py-0.5 rounded border border-violet-500/25 uppercase"><Globe className="h-2 w-2" />Remote</span>
        : <span className="flex items-center gap-1 text-[9px] bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded border border-zinc-700 uppercase"><Terminal className="h-2 w-2" />Local</span>
);

const toastStyles: Record<string, string> = {
    success: 'bg-green-500/10 border-green-500/30 text-green-400',
    warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
    error: 'bg-red-500/10   border-red-500/30   text-red-400',
};
const ToastIcon: Record<string, React.ElementType> = {
    success: CheckCircle, warning: AlertCircle, error: XCircle,
};

const inputCls = "w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700";
const monoInputCls = `${inputCls} font-mono`;

// ── Main component ─────────────────────────────────────────────────────────────

export const McpServersTab = ({
    mcpServers, loadingMcp, isConnecting, lastConnected,
    mcpToast, setMcpToast,
    pendingServerName, onPendingResolved,
    draftMcpServer, setDraftMcpServer,
    onAddServer, onDeleteServer, onReconnectServer,
}: McpServersTabProps) => {
    const dispatch = useDispatch<AppDispatch>();

    // Track which form panel is active (controlled by draftMcpServer.server_type)
    const serverType = draftMcpServer.server_type;
    const setServerType = (t: 'stdio' | 'remote') =>
        setDraftMcpServer({ ...draftMcpServer, server_type: t });

    // ── Refresh ────────────────────────────────────────────────────────────────
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [tokenVisible, setTokenVisible] = useState(true);

    const refreshServers = async (silent = false) => {
        if (!silent) setIsRefreshing(true);
        try {
            const res = await fetch('/api/mcp/servers');
            if (res.ok) {
                const servers = await res.json();
                dispatch(setMcpServers(Array.isArray(servers) ? servers : []));
            }
        } catch { /* silent */ } finally {
            if (!silent) setIsRefreshing(false);
        }
    };

    // ── Polling for pending OAuth remote server ────────────────────────────
    // Active only when this tab is visible and pendingServerName is set.
    // Polls /api/mcp/servers every 5 s for up to 60 s; stops on connected.
    const [pollCountdown, setPollCountdown] = useState(0);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollEndRef = useRef(0);

    const stopPolling = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
        setPollCountdown(0);
    };

    useEffect(() => {
        if (!pendingServerName) { stopPolling(); return; }

        pollEndRef.current = Date.now() + 60_000;
        setPollCountdown(60);

        pollRef.current = setInterval(async () => {
            try {
                const res = await fetch('/api/mcp/servers');
                if (!res.ok) return;
                const servers: any[] = await res.json();
                dispatch(setMcpServers(servers));
                const target = servers.find((s: any) => s.name === pendingServerName);
                if (target?.status === 'connected') {
                    stopPolling();
                    onPendingResolved();
                    setMcpToast({ show: true, message: `✓ ${pendingServerName} connected!`, type: 'success' });
                    setTimeout(() => setMcpToast(null), 5000);
                    return;
                }
            } catch { /* ignore */ }
            if (Date.now() >= pollEndRef.current) {
                stopPolling();
                onPendingResolved();
            }
        }, 5_000);

        tickRef.current = setInterval(() => {
            const remaining = Math.max(0, Math.round((pollEndRef.current - Date.now()) / 1000));
            setPollCountdown(remaining);
            if (remaining <= 0) { stopPolling(); onPendingResolved(); }
        }, 1_000);

        return stopPolling;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pendingServerName]);

    // ── Preset helper ──────────────────────────────────────────────────────────
    const applyPreset = (p: Preset) => {
        const env = p.env
            ? Object.entries(p.env).map(([key, value]) => ({ key, value }))
            : [];
        setDraftMcpServer({
            name: p.name,
            label: p.label,
            server_type: p.server_type,
            command: p.command || '',
            args: p.args || '',
            env,
            url: p.url || '',
            token: p.token || '',
        });
    };

    // ── Env var helpers ────────────────────────────────────────────────────────
    const addEnvVar = () => setDraftMcpServer({ ...draftMcpServer, env: [...draftMcpServer.env, { key: '', value: '' }] });
    const removeEnvVar = (i: number) => setDraftMcpServer({ ...draftMcpServer, env: draftMcpServer.env.filter((_, idx) => idx !== i) });
    const updateEnvVar = (i: number, field: 'key' | 'value', val: string) => {
        const newEnv = [...draftMcpServer.env];
        newEnv[i] = { ...newEnv[i], [field]: val };
        setDraftMcpServer({ ...draftMcpServer, env: newEnv });
    };

    // ── Render ─────────────────────────────────────────────────────────────────
    return (
        <div className="space-y-8">

            {/* ── Header ── */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <Server className="h-5 w-5" /> External MCP Servers
                    </h3>
                    <p className="text-zinc-500 text-sm mt-1">
                        Connect local and remote Model Context Protocol servers to extend agent capabilities.
                    </p>
                </div>
                <button
                    onClick={() => refreshServers()}
                    disabled={isRefreshing}
                    title="Refresh server statuses"
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white rounded transition-colors disabled:opacity-50 shrink-0 mt-1"
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                    {isRefreshing ? 'Refreshing…' : 'Refresh'}
                </button>
            </div>

            {/* ── Inline Toast ── */}
            {mcpToast?.show && (
                <div className={`flex items-start gap-2.5 px-4 py-3 rounded border text-xs font-medium animate-in fade-in slide-in-from-top-2 duration-200 ${toastStyles[mcpToast.type]}`}>
                    {(() => { const Icon = ToastIcon[mcpToast.type]; return <Icon className="h-4 w-4 mt-0.5 shrink-0" />; })()}
                    <span className="leading-relaxed">{mcpToast.message}</span>
                </div>
            )}

            {/* ── Connected Servers List ── */}
            <div className="space-y-4">
                <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Connected Servers</h4>
                {loadingMcp ? (
                    <div className="flex items-center gap-2 text-zinc-500 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
                    </div>
                ) : mcpServers.length === 0 ? (
                    <div className="p-8 text-center border border-dashed border-zinc-800 rounded bg-zinc-900/30">
                        <Server className="h-8 w-8 mx-auto text-zinc-700 mb-2" />
                        <p className="text-zinc-500 text-sm">No servers added yet.</p>
                        <p className="text-zinc-700 text-xs mt-1">Pick a preset or fill the form below.</p>
                    </div>
                ) : (
                    <div className="grid gap-3">
                        {mcpServers.map((server) => (
                            <div key={server.name} className="flex items-center justify-between p-4 bg-zinc-900 border border-zinc-800 rounded group">
                                <div className="flex flex-col gap-1.5 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-bold text-white text-sm">{server.label || server.name}</span>
                                        {server.label && server.label !== server.name && (
                                            <span className="text-[10px] text-zinc-600 font-mono">{server.name}</span>
                                        )}
                                        <TypePill type={server.server_type} />
                                        <StatusBadge status={server.status} />
                                    </div>
                                    <code className="text-[10px] text-zinc-500 font-mono truncate">
                                        {server.server_type === 'remote'
                                            ? server.url
                                            : `${server.command} ${(server.args || []).join(' ')}`}
                                    </code>
                                </div>
                                <div className="flex items-center gap-1 ml-4 shrink-0">
                                    {server.status === 'connecting' && (
                                        <span className="p-2"><Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" /></span>
                                    )}
                                    {(!server.status || server.status === 'disconnected') && (
                                        <button onClick={() => onReconnectServer(server.name)} title="Retry connection"
                                            className="p-2 text-zinc-500 hover:text-blue-400 hover:bg-zinc-800 rounded transition-colors">
                                            <RefreshCw className="h-3.5 w-3.5" />
                                        </button>
                                    )}
                                    <button onClick={() => onDeleteServer(server.name)}
                                        className="p-2 text-zinc-600 hover:text-red-500 hover:bg-zinc-800 rounded transition-colors">
                                        <Trash className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ── Add Server Form ── */}
            <div className="pt-6 border-t border-zinc-800 space-y-6">

                {/* Type toggle */}
                <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 p-1 w-fit">
                    <button
                        onClick={() => setServerType('stdio')}
                        className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold transition-colors ${serverType === 'stdio' ? 'bg-white text-black' : 'text-zinc-500 hover:text-white'}`}
                    >
                        <Terminal className="h-3 w-3" /> Local (stdio)
                    </button>
                    <button
                        onClick={() => setServerType('remote')}
                        className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold transition-colors ${serverType === 'remote' ? 'bg-white text-black' : 'text-zinc-500 hover:text-white'}`}
                    >
                        <Globe className="h-3 w-3" /> Remote (URL)
                    </button>
                </div>

                {/* ── Presets ── */}
                <div className="space-y-3">
                    <div className="flex items-center gap-2">
                        <Zap className="h-3.5 w-3.5 text-zinc-500" />
                        <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">
                            {serverType === 'stdio' ? 'Local Presets' : 'Remote Presets'}
                        </h4>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {(serverType === 'stdio' ? STDIO_PRESETS : REMOTE_PRESETS).map(p => (
                            <button key={p.name + p.label} onClick={() => applyPreset(p)}
                                className="px-3 py-1.5 text-[11px] font-medium bg-zinc-900 border border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-white rounded transition-colors">
                                {p.label}
                            </button>
                        ))}
                    </div>
                    <p className="text-[10px] text-zinc-600">
                        Find more on the{' '}
                        <a href="https://github.com/modelcontextprotocol/servers" target="_blank" rel="noopener noreferrer"
                            className="text-zinc-400 underline underline-offset-2 hover:text-white transition-colors">
                            MCP servers registry
                        </a>.
                        {serverType === 'remote' && ' Remote servers use native OAuth — no npx required.'}
                    </p>
                </div>

                {/* ── Fields ── */}
                <div className="space-y-4">
                    {/* Display Label + Unique ID — always shown */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label className="text-[10px] uppercase font-bold text-zinc-500">Display Label</label>
                            <input type="text" value={draftMcpServer.label}
                                onChange={e => setDraftMcpServer({ ...draftMcpServer, label: e.target.value })}
                                className={inputCls} placeholder="e.g. GitHub Production" />
                        </div>
                        <div className="space-y-2">
                            <label className="text-[10px] uppercase font-bold text-zinc-500">Unique ID</label>
                            <input type="text" value={draftMcpServer.name}
                                onChange={e => setDraftMcpServer({ ...draftMcpServer, name: e.target.value })}
                                className={inputCls} placeholder="e.g. github-prod" />
                        </div>
                    </div>

                    {serverType === 'stdio' ? (
                        /* ── stdio fields ── */
                        <>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Command</label>
                                    <input type="text" value={draftMcpServer.command}
                                        onChange={e => setDraftMcpServer({ ...draftMcpServer, command: e.target.value })}
                                        className={monoInputCls} placeholder="npx, uvx, python3" />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Arguments</label>
                                    <input type="text" value={draftMcpServer.args}
                                        onChange={e => setDraftMcpServer({ ...draftMcpServer, args: e.target.value })}
                                        className={monoInputCls} placeholder="-y @org/server-name" />
                                </div>
                            </div>

                            {/* Env vars */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <label className="text-[10px] uppercase font-bold text-zinc-500">Environment Variables</label>
                                    <button onClick={addEnvVar}
                                        className="text-[10px] font-bold text-zinc-400 hover:text-white flex items-center gap-1">
                                        <Plus className="h-3 w-3" /> ADD VAR
                                    </button>
                                </div>
                                {draftMcpServer.env.map((env, i) => (
                                    <div key={i} className="flex gap-2">
                                        <input type="text" placeholder="KEY" value={env.key}
                                            onChange={e => updateEnvVar(i, 'key', e.target.value)}
                                            className="flex-1 bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none" />
                                        <input type="text" placeholder="VALUE" value={env.value}
                                            onChange={e => updateEnvVar(i, 'value', e.target.value)}
                                            className="flex-[2] bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none" />
                                        <button onClick={() => removeEnvVar(i)} className="p-2 text-zinc-600 hover:text-red-500">
                                            <Trash className="h-4 w-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </>
                    ) : (
                        /* ── remote fields ── */
                        <>
                            <div className="space-y-2">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Server URL</label>
                                <input type="url" value={draftMcpServer.url}
                                    onChange={e => setDraftMcpServer({ ...draftMcpServer, url: e.target.value })}
                                    className={monoInputCls} placeholder="https://mcp.example.com/mcp" />
                                <p className="text-[10px] text-zinc-600">
                                    Leave token empty to use OAuth (browser will open). Fill token for PAT-based servers (Figma, GitHub).
                                </p>
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] uppercase font-bold text-zinc-500">Bearer Token / Personal Access Token <span className="text-zinc-600 normal-case font-normal">(optional — leave empty for OAuth)</span></label>
                                <div className="relative">
                                    <input
                                        type={tokenVisible ? 'text' : 'password'}
                                        value={draftMcpServer.token}
                                        onChange={e => setDraftMcpServer({ ...draftMcpServer, token: e.target.value })}
                                        className={`${monoInputCls} pr-10`}
                                        placeholder="ghp_... or fig_... or leave empty"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setTokenVisible(v => !v)}
                                        title={tokenVisible ? 'Hide token' : 'Show token'}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                                    >
                                        {tokenVisible
                                            ? <EyeOff className="h-4 w-4" />
                                            : <Eye className="h-4 w-4" />}
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Submit */}
                <div className="flex justify-end pt-2">
                    <button onClick={onAddServer} disabled={isConnecting}
                        className="flex items-center gap-2 px-6 py-2 bg-white text-black text-sm font-bold hover:bg-zinc-200 transition-colors disabled:opacity-60 disabled:cursor-not-allowed">
                        {isConnecting
                            ? <><Loader2 className="h-4 w-4 animate-spin" /> Connecting…</>
                            : 'Connect Server'}
                    </button>
                </div>
            </div>
        </div>
    );
};
