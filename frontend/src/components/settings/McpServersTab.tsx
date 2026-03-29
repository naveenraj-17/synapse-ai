/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from 'react';
import { Server, Plus, Trash, RefreshCw, Loader2, CheckCircle, XCircle, AlertCircle, Zap } from 'lucide-react';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '@/store';
import { setMcpServers, updateMcpServerStatus } from '@/store/settingsSlice';

interface McpToast {
    show: boolean;
    message: string;
    type: 'success' | 'warning' | 'error';
}

interface McpServersTabProps {
    mcpServers: any[];
    loadingMcp: boolean;
    isConnecting: boolean;
    lastConnected: boolean | null;  // null = no attempt yet, true/false = last result
    mcpToast: McpToast | null;
    draftMcpServer: { name: string; command: string; args: string; env: { key: string; value: string }[] };
    setDraftMcpServer: (v: { name: string; command: string; args: string; env: { key: string; value: string }[] }) => void;
    onAddServer: () => void;
    onDeleteServer: (name: string) => void;
    onReconnectServer: (name: string) => void;
}

interface Preset {
    name: string;
    command: string;
    args: string;
    label: string;
    env?: Record<string, string>;
}

const PRESETS: Preset[] = [
    { name: 'Git', command: 'uvx', args: 'mcp-server-git', label: 'Git' },
    { name: 'Vercel', command: 'npx', args: 'mcp-remote https://mcp.vercel.com', label: 'Vercel' },
    {
        name: 'Github',
        command: 'npx',
        args: '-y @modelcontextprotocol/server-github',
        label: 'GitHub',
        env: { GITHUB_PERSONAL_ACCESS_TOKEN: '' },
    },
    { name: 'Jira', command: 'npx', args: 'mcp-remote https://mcp.atlassian.com/v1/mcp', label: 'Jira' },
    { name: 'Zapier', command: 'npx', args: 'mcp-remote https://mcp.zapier.com/api/mcp/mcp', label: 'Zapier' },
    {
        name: 'Figma',
        command: 'npx',
        args: 'mcp-remote https://mcp.figma.com/mcp --header "Authorization:Bearer ${FIGMA_PERSONAL_ACCESS_TOKEN}"',
        label: 'Figma',
        env: { FIGMA_PERSONAL_ACCESS_TOKEN: '' },
    },
    { name: 'Fetch', command: 'npx', args: 'mcp-remote https://remote.mcpservers.org/fetch/mcp', label: 'Fetch' },
];

// ─── Sub-components ────────────────────────────────────────────────────────────

const StatusBadge = ({ status, isConnecting }: { status?: string; isConnecting?: boolean }) => {
    if (isConnecting || status === 'connecting') {
        return (
            <span className="flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30 uppercase">
                <Loader2 className="h-2.5 w-2.5 animate-spin" /> Connecting
            </span>
        );
    }
    if (status === 'connected') {
        return (
            <span className="flex items-center gap-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30 uppercase">
                <CheckCircle className="h-2.5 w-2.5" /> Active
            </span>
        );
    }
    return (
        <span className="flex items-center gap-1 text-[10px] bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded border border-yellow-500/30 uppercase">
            <XCircle className="h-2.5 w-2.5" /> Disconnected
        </span>
    );
};

const toastStyles: Record<string, string> = {
    success: 'bg-green-500/10 border-green-500/30 text-green-400',
    warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
    error: 'bg-red-500/10 border-red-500/30 text-red-400',
};
const toastIcon: Record<string, React.ElementType> = {
    success: CheckCircle,
    warning: AlertCircle,
    error: XCircle,
};

// ─── Main component ────────────────────────────────────────────────────────────

export const McpServersTab = ({
    mcpServers, loadingMcp, isConnecting, lastConnected, mcpToast, draftMcpServer, setDraftMcpServer,
    onAddServer, onDeleteServer, onReconnectServer
}: McpServersTabProps) => {
    const dispatch = useDispatch<AppDispatch>();

    // ── Refresh / polling state ───────────────────────────────────────────────
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [pollingActive, setPollingActive] = useState(false);
    const [pollCountdown, setPollCountdown] = useState(0); // seconds remaining
    const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollEndRef = useRef<number>(0);

    // ── Refresh: fetch latest server list from backend ────────────────────────
    const refreshServers = async (silent = false) => {
        if (!silent) setIsRefreshing(true);
        try {
            const res = await fetch('/api/mcp/servers');
            if (res.ok) {
                const servers = await res.json();
                dispatch(setMcpServers(Array.isArray(servers) ? servers : []));
                // Also try to sync statuses from the available-tools endpoint
                // (the backend tracks active sessions there)
                const toolsRes = await fetch('/api/tools/available');
                if (toolsRes.ok) {
                    const toolsData = await toolsRes.json();
                    const activeSources = new Set<string>(
                        (toolsData.tools || [])
                            .filter((t: any) => t.type === 'mcp_external')
                            .map((t: any) => t.source as string)
                    );
                    // Mark each server connected/disconnected based on active sessions
                    (Array.isArray(servers) ? servers : []).forEach((s: any) => {
                        const isActive = activeSources.has(s.name);
                        dispatch(updateMcpServerStatus({ name: s.name, status: isActive ? 'connected' : 'disconnected' }));
                    });
                }
            }
        } catch { /* silent */ } finally {
            if (!silent) setIsRefreshing(false);
        }
    };

    // ── Start polling for 60 s after a server is added ────────────────────────
    const startPolling = () => {
        stopPolling();
        setPollingActive(true);
        pollEndRef.current = Date.now() + 60_000;
        setPollCountdown(60);

        // Poll every 5 s
        pollIntervalRef.current = setInterval(async () => {
            await refreshServers(true);
            if (Date.now() >= pollEndRef.current) stopPolling();
        }, 5_000);

        // Countdown ticker every 1 s
        pollTimerRef.current = setInterval(() => {
            const remaining = Math.max(0, Math.round((pollEndRef.current - Date.now()) / 1000));
            setPollCountdown(remaining);
            if (remaining <= 0) stopPolling();
        }, 1_000);
    };

    const stopPolling = () => {
        if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; }
        if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null; }
        setPollingActive(false);
        setPollCountdown(0);
    };

    // Start polling only when connection attempt finished with connected=false (OAuth pending)
    const prevIsConnecting = useRef(false);
    useEffect(() => {
        if (prevIsConnecting.current && !isConnecting) {
            // Connection finished — only poll if it didn't succeed
            if (lastConnected === false) {
                startPolling();
            } else {
                // Already connected — no need to poll
                stopPolling();
            }
        }
        prevIsConnecting.current = isConnecting;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isConnecting, lastConnected]);

    // Cleanup on unmount
    useEffect(() => () => stopPolling(), []);

    // ── Preset helpers ────────────────────────────────────────────────────────
    const applyPreset = (preset: Preset) => {
        const env = preset.env
            ? Object.entries(preset.env).map(([key, value]) => ({ key, value }))
            : [];
        setDraftMcpServer({ name: preset.name, command: preset.command, args: preset.args, env });
    };

    // ─────────────────────────────────────────────────────────────────────────
    return (
        <div className="space-y-8">

            {/* ── Header ── */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <Server className="h-5 w-5" />
                        External MCP Servers
                    </h3>
                    <p className="text-zinc-500 text-sm mt-1">
                        Connect external Model Context Protocol (MCP) servers to extend agent capabilities.
                    </p>
                </div>

                {/* Refresh button + polling indicator */}
                <div className="flex items-center gap-2 shrink-0 mt-1">
                    {pollingActive && (
                        <span className="text-[10px] text-blue-400 font-mono tabular-nums">
                            auto-refresh {pollCountdown}s
                        </span>
                    )}
                    <button
                        onClick={() => refreshServers()}
                        disabled={isRefreshing}
                        title="Refresh server statuses"
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                        {isRefreshing ? 'Refreshing…' : 'Refresh'}
                    </button>
                </div>
            </div>

            {/* ── Inline Toast ── */}
            {mcpToast?.show && (
                <div className={`flex items-start gap-2.5 px-4 py-3 rounded border text-xs font-medium animate-in fade-in slide-in-from-top-2 duration-200 ${toastStyles[mcpToast.type]}`}>
                    {(() => { const Icon = toastIcon[mcpToast.type]; return <Icon className="h-4 w-4 mt-0.5 shrink-0" />; })()}
                    <span className="leading-relaxed">{mcpToast.message}</span>
                </div>
            )}

            {/* ── Connected Servers List ── */}
            <div className="space-y-4">
                <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Connected Servers</h4>
                {loadingMcp ? (
                    <div className="flex items-center gap-2 text-zinc-500 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" /> Loading servers…
                    </div>
                ) : mcpServers.length === 0 ? (
                    <div className="p-8 text-center border border-dashed border-zinc-800 rounded bg-zinc-900/30">
                        <Server className="h-8 w-8 mx-auto text-zinc-700 mb-2" />
                        <p className="text-zinc-500 text-sm">No servers added yet.</p>
                        <p className="text-zinc-700 text-xs mt-1">Pick a preset below or fill in the form.</p>
                    </div>
                ) : (
                    <div className="grid gap-3">
                        {mcpServers.map((server) => {
                            const isServerConnecting = server.status === 'connecting';
                            const isDisconnected = !server.status || server.status === 'disconnected';
                            return (
                                <div
                                    key={server.name}
                                    className="flex items-center justify-between p-4 bg-zinc-900 border border-zinc-800 rounded group"
                                >
                                    <div className="flex flex-col gap-1.5 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-bold text-white text-sm">{server.name}</span>
                                            <StatusBadge status={server.status} isConnecting={isServerConnecting} />
                                        </div>
                                        <code className="text-[10px] text-zinc-500 font-mono truncate">
                                            {server.command} {(server.args || []).join(' ')}
                                        </code>
                                    </div>

                                    <div className="flex items-center gap-1 ml-4 shrink-0">
                                        {isServerConnecting && (
                                            <span className="p-2">
                                                <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" />
                                            </span>
                                        )}
                                        {isDisconnected && (
                                            <button
                                                onClick={() => onReconnectServer(server.name)}
                                                title="Retry connection"
                                                className="p-2 text-zinc-500 hover:text-blue-400 hover:bg-zinc-800 rounded transition-colors"
                                            >
                                                <RefreshCw className="h-3.5 w-3.5" />
                                            </button>
                                        )}
                                        <button
                                            onClick={() => onDeleteServer(server.name)}
                                            className="p-2 text-zinc-600 hover:text-red-500 hover:bg-zinc-800 rounded transition-colors"
                                        >
                                            <Trash className="h-4 w-4" />
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* ── Quick Presets ── */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <Zap className="h-3.5 w-3.5 text-zinc-500" />
                    <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Quick Presets</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                    {PRESETS.map(preset => (
                        <button
                            key={preset.name}
                            onClick={() => applyPreset(preset)}
                            className="px-3 py-1.5 text-[11px] font-medium bg-zinc-900 border border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-white rounded transition-colors"
                        >
                            {preset.label}
                        </button>
                    ))}
                </div>
                <p className="text-[10px] text-zinc-600">
                    Find more MCP servers on the{' '}
                    <a
                        href="https://github.com/modelcontextprotocol/servers"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-400 underline underline-offset-2 hover:text-white transition-colors"
                    >
                        MCP servers registry
                    </a>
                    .
                </p>
            </div>

            {/* ── Add Server Form ── */}
            <div className="pt-6 border-t border-zinc-800 space-y-6">
                <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Add New Server</h4>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Server Name</label>
                        <input
                            type="text"
                            value={draftMcpServer.name}
                            onChange={e => setDraftMcpServer({ ...draftMcpServer, name: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700"
                            placeholder="e.g. filesystem"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Command</label>
                        <input
                            type="text"
                            value={draftMcpServer.command}
                            onChange={e => setDraftMcpServer({ ...draftMcpServer, command: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700"
                            placeholder="e.g. npx, uvx, python3"
                        />
                    </div>
                    <div className="col-span-2 space-y-2">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Arguments</label>
                        <input
                            type="text"
                            value={draftMcpServer.args}
                            onChange={e => setDraftMcpServer({ ...draftMcpServer, args: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700"
                            placeholder="-y @modelcontextprotocol/server-filesystem /path"
                        />
                        <p className="text-[10px] text-zinc-600">
                            Space-separated arguments. For OAuth servers (Vercel, GitHub, Figma…) a browser tab will open — complete auth, then use the <RefreshCw className="inline h-2.5 w-2.5 mb-0.5" /> Retry button.
                        </p>
                    </div>
                </div>

                {/* Env vars */}
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Environment Variables</label>
                        <button
                            onClick={() => setDraftMcpServer({ ...draftMcpServer, env: [...draftMcpServer.env, { key: '', value: '' }] })}
                            className="text-[10px] font-bold text-zinc-400 hover:text-white flex items-center gap-1"
                        >
                            <Plus className="h-3 w-3" /> ADD VAR
                        </button>
                    </div>
                    {draftMcpServer.env.map((env, idx) => (
                        <div key={idx} className="flex gap-2">
                            <input
                                type="text"
                                placeholder="KEY"
                                value={env.key}
                                onChange={e => {
                                    const newEnv = [...draftMcpServer.env];
                                    newEnv[idx] = { ...newEnv[idx], key: e.target.value };
                                    setDraftMcpServer({ ...draftMcpServer, env: newEnv });
                                }}
                                className="flex-1 bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none"
                            />
                            <input
                                type="text"
                                placeholder="VALUE"
                                value={env.value}
                                onChange={e => {
                                    const newEnv = [...draftMcpServer.env];
                                    newEnv[idx] = { ...newEnv[idx], value: e.target.value };
                                    setDraftMcpServer({ ...draftMcpServer, env: newEnv });
                                }}
                                className="flex-[2] bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none"
                            />
                            <button
                                onClick={() => setDraftMcpServer({ ...draftMcpServer, env: draftMcpServer.env.filter((_, i) => i !== idx) })}
                                className="p-2 text-zinc-600 hover:text-red-500"
                            >
                                <Trash className="h-4 w-4" />
                            </button>
                        </div>
                    ))}
                </div>

                {/* Submit row */}
                <div className="flex justify-end pt-4">
                    <button
                        onClick={onAddServer}
                        disabled={isConnecting}
                        className="flex items-center gap-2 px-6 py-2 bg-white text-black text-sm font-bold hover:bg-zinc-200 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                        {isConnecting ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Connecting…
                            </>
                        ) : 'Connect Server'}
                    </button>
                </div>
            </div>
        </div>
    );
};
