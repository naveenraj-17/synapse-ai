/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useEffect, useCallback } from 'react';
import {
    MessageSquare, Plus, Trash, Save, Play, Square, FlaskConical,
    ChevronDown, ChevronRight, AlertTriangle, CheckCircle, XCircle,
    Loader2, Info, RefreshCw,
} from 'lucide-react';
import { ConfirmationModal } from './ConfirmationModal';

// ─── Types ────────────────────────────────────────────────────────────────────

type Platform = 'telegram' | 'discord' | 'slack' | 'teams' | 'whatsapp';

interface Channel {
    id?: string;
    name: string;
    platform: Platform;
    agent_id: string;
    multi_agent_mode: boolean;
    enabled: boolean;
    credentials: Record<string, string>;
    status?: 'running' | 'stopped' | 'error';
    last_error?: string | null;
}

const EMPTY_CHANNEL: Channel = {
    name: '',
    platform: 'telegram',
    agent_id: '',
    multi_agent_mode: false,
    enabled: true,
    credentials: {},
};

// ─── Platform metadata ────────────────────────────────────────────────────────

const PLATFORMS: { id: Platform; label: string; color: string; icon: string }[] = [
    { id: 'telegram', label: 'Telegram', color: 'text-sky-400 border-sky-800 bg-sky-950/40', icon: '/telegram-icon.svg' },
    { id: 'discord', label: 'Discord', color: 'text-indigo-400 border-indigo-800 bg-indigo-950/40', icon: '/discord-round-color-icon.svg' },
    { id: 'slack', label: 'Slack', color: 'text-green-400 border-green-800 bg-green-950/40', icon: '/slack-icon.svg' },
    { id: 'teams', label: 'Teams', color: 'text-blue-400 border-blue-800 bg-blue-950/40', icon: '/teams.svg' },
    { id: 'whatsapp', label: 'WhatsApp', color: 'text-emerald-400 border-emerald-800 bg-emerald-950/40', icon: '/whatsapp-color-icon.svg' },
];

// ─── Credential field definitions per platform ────────────────────────────────

const CREDENTIAL_FIELDS: Record<Platform, { key: string; label: string; placeholder: string; secret?: boolean; note?: string }[]> = {
    telegram: [
        { key: 'bot_token', label: 'Bot Token', placeholder: '123456:ABC-DEF...', secret: true, note: 'Get from @BotFather on Telegram' },
    ],
    discord: [
        { key: 'bot_token', label: 'Bot Token', placeholder: 'MTE...', secret: true, note: 'From Discord Developer Portal → Bot → Token' },
        { key: 'channel_id', label: 'Restrict to Channel ID (optional)', placeholder: '123456789012345678', note: 'Leave empty to respond in all channels where the bot is mentioned' },
    ],
    slack: [
        { key: 'bot_token', label: 'Bot Token (xoxb-...)', placeholder: 'xoxb-...', secret: true, note: 'OAuth & Permissions → Bot Token Scopes' },
        { key: 'app_token', label: 'App-Level Token (xapp-...)', placeholder: 'xapp-...', secret: true, note: 'Enable Socket Mode → generate App-Level Token with connections:write scope' },
    ],
    teams: [
        { key: 'app_id', label: 'Azure App ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', note: 'Azure Bot resource → Configuration → Microsoft App ID' },
        { key: 'app_password', label: 'App Password / Client Secret', placeholder: '', secret: true, note: 'Azure Bot → Certificates & Secrets' },
    ],
    whatsapp: [
        // These are conditionally rendered based on whatsapp_mode — see component
    ],
};

// ─── Setup guides per platform ────────────────────────────────────────────────

const SETUP_GUIDES: Record<Platform, { title: string; steps: string[] }> = {
    telegram: {
        title: 'Creating a Telegram Bot',
        steps: [
            'Open Telegram and search for @BotFather',
            'Send /newbot and follow the prompts to name your bot',
            'Copy the bot token shown (format: 123456:ABC-DEF...)',
            'Paste it in the Bot Token field above',
            'Click Save & Connect — the bot will start polling immediately',
        ],
    },
    discord: {
        title: 'Creating a Discord Bot',
        steps: [
            'Go to discord.com/developers/applications → New Application',
            'In the Bot tab, click Add Bot → copy the Token',
            'Enable Message Content Intent under Privileged Gateway Intents',
            'In OAuth2 → URL Generator: select bot + applications.commands, check Read/Send Messages',
            'Use the generated URL to invite the bot to your server',
            'Paste the bot token above and optionally restrict to a channel ID',
        ],
    },
    slack: {
        title: 'Creating a Slack App with Socket Mode',
        steps: [
            'Go to api.slack.com/apps → Create New App → From Scratch',
            'In Socket Mode, enable it and generate an App-Level Token (xapp-...) with connections:write scope',
            'In Event Subscriptions → Subscribe to bot events: message.im, app_mention',
            'In OAuth & Permissions add scopes: app_mentions:read, chat:write, im:history, im:write, channels:history',
            'Install to workspace and copy the Bot Token (xoxb-...)',
            'Paste both tokens above',
        ],
    },
    teams: {
        title: 'Creating a Microsoft Teams Bot',
        steps: [
            'Go to portal.azure.com → Create a resource → Azure Bot',
            'Set the Messaging endpoint to: https://<your-ngrok-url>/api/messaging/teams/webhook/<channel-id>',
            'For local dev, run: ngrok http 8000  and use the Forwarding URL',
            'Note: only the Synapse backend needs the public URL — your frontend is unaffected',
            'In the bot Configuration, copy the Microsoft App ID',
            'In Certificates & Secrets, create a new client secret and copy it',
            'Add the Teams channel in the bot\'s Channels tab',
        ],
    },
    whatsapp: {
        title: 'WhatsApp Setup',
        steps: [
            'BUSINESS ACCOUNT PATH: Go to developers.facebook.com → My Apps → Create App (type: Business)',
            'Add WhatsApp product → Phone Numbers → select a test or production number',
            'In WhatsApp → Configuration, set Webhook URL to: https://<ngrok-url>/api/messaging/whatsapp/webhook/<channel-id>',
            'Set your Verify Token (any string), subscribe to the messages webhook field',
            'Copy the Phone Number ID and generate a temporary/permanent Access Token',
            '--- OR ---',
            'UNOFFICIAL PATH: No business account needed. Synapse will open WhatsApp Web in a browser window and you scan the QR code to authenticate. This may violate WhatsApp\'s Terms of Service.',
        ],
    },
};

// ─── Status badge ─────────────────────────────────────────────────────────────

const StatusBadge = ({ status, lastError }: { status?: string; lastError?: string | null }) => {
    if (status === 'running') return (
        <span className="flex items-center gap-1 text-[10px] font-bold text-green-400 bg-green-950/50 border border-green-900 px-2 py-0.5">
            <CheckCircle className="h-2.5 w-2.5" /> RUNNING
        </span>
    );
    if (status === 'error') return (
        <span className="flex items-center gap-1 text-[10px] font-bold text-red-400 bg-red-950/50 border border-red-900 px-2 py-0.5" title={lastError || ''}>
            <XCircle className="h-2.5 w-2.5" /> ERROR
        </span>
    );
    return (
        <span className="flex items-center gap-1 text-[10px] font-bold text-zinc-500 bg-zinc-900 border border-zinc-800 px-2 py-0.5">
            <Square className="h-2.5 w-2.5" /> STOPPED
        </span>
    );
};

// ─── Main component ───────────────────────────────────────────────────────────

export const MessagingTab = () => {
    const [channels, setChannels] = useState<Channel[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [draft, setDraft] = useState<Channel | null>(null);
    const [agents, setAgents] = useState<any[]>([]);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [toastMsg, setToastMsg] = useState<string | null>(null);
    const [guideOpen, setGuideOpen] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    // WhatsApp sub-mode UI state
    const [waMode, setWaMode] = useState<'meta_api' | 'unofficial'>('meta_api');
    const [waRiskAck, setWaRiskAck] = useState(false);
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

    const showToast = (msg: string) => {
        setToastMsg(msg);
        setTimeout(() => setToastMsg(null), 3000);
    };

    const fetchChannels = useCallback(async () => {
        setRefreshing(true);
        try {
            const res = await fetch('/api/messaging/channels');
            if (res.ok) {
                const data = await res.json();
                setChannels(Array.isArray(data) ? data : []);
            }
        } catch {
            // ignore — messaging may not be enabled
        } finally {
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        fetchChannels();
        fetch('/api/agents').then(r => r.json()).then(d => setAgents(Array.isArray(d) ? d : [])).catch(() => {});
    }, [fetchChannels]);

    const selectChannel = (ch: Channel) => {
        setSelectedId(ch.id || null);
        setDraft({ ...ch });
        setGuideOpen(false);
        if (ch.platform === 'whatsapp') {
            setWaMode((ch.credentials?.whatsapp_mode as any) || 'meta_api');
            setWaRiskAck(false);
        }
    };

    const newChannel = () => {
        setSelectedId(null);
        setDraft({ ...EMPTY_CHANNEL });
        setGuideOpen(false);
        setWaMode('meta_api');
        setWaRiskAck(false);
    };

    const saveAndConnect = async () => {
        if (!draft) return;
        if (!draft.name.trim()) { showToast('Please enter a channel name'); return; }
        if (!draft.agent_id) { showToast('Please select an agent'); return; }

        setSaving(true);
        try {
            // Inject waMode into credentials for whatsapp
            const payload = draft.platform === 'whatsapp'
                ? { ...draft, credentials: { ...draft.credentials, whatsapp_mode: waMode } }
                : draft;

            const res = await fetch('/api/messaging/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error('Save failed');
            const saved = await res.json();

            // Enable
            await fetch(`/api/messaging/channels/${saved.id}/enable`, { method: 'POST' });

            await fetchChannels();
            setSelectedId(saved.id);
            setDraft({ ...saved });
            showToast('✅ Channel saved and started');
        } catch (e: any) {
            showToast(`❌ ${e.message}`);
        } finally {
            setSaving(false);
        }
    };

    const testChannel = async () => {
        if (!selectedId) return;
        setTesting(true);
        try {
            const res = await fetch(`/api/messaging/channels/${selectedId}/test`, { method: 'POST' });
            const data = await res.json();
            showToast(data.status === 'ok' ? `✅ ${data.message}` : `⚠️ ${data.message}`);
        } catch {
            showToast('❌ Test failed');
        } finally {
            setTesting(false);
        }
    };

    const toggleEnable = async (ch: Channel) => {
        if (!ch.id) return;
        const endpoint = ch.status === 'running' ? 'disable' : 'enable';
        await fetch(`/api/messaging/channels/${ch.id}/${endpoint}`, { method: 'POST' });
        await fetchChannels();
    };

    const deleteChannel = async (id: string) => {
        const ch = channels.find(c => c.id === id);
        if (!ch || !ch.id) return;
        await fetch(`/api/messaging/channels/${ch.id}`, { method: 'DELETE' });
        if (selectedId === ch.id) { setSelectedId(null); setDraft(null); }
        await fetchChannels();
    };

    const updateCred = (key: string, value: string) => {
        if (!draft) return;
        setDraft({ ...draft, credentials: { ...draft.credentials, [key]: value } });
    };

    const platform = draft?.platform || 'telegram';
    const platformMeta = PLATFORMS.find(p => p.id === platform)!;
    const guide = SETUP_GUIDES[platform];

    return (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-10">
            {/* Toast */}
            {toastMsg && (
                <div className="fixed bottom-6 right-6 z-50 bg-zinc-900 border border-zinc-700 text-white text-xs px-4 py-3 shadow-xl animate-in slide-in-from-bottom-4">
                    {toastMsg}
                </div>
            )}

            {/* ── Left: Channel List ─────────────────────────────────── */}
            <div className="md:col-span-4 border-r border-zinc-800 pr-4 flex flex-col max-h-[calc(100vh-180px)] sticky top-0 self-start">
                <div className="mb-4 flex justify-between items-center">
                    <h3 className="text-sm font-bold text-zinc-400">CHANNELS</h3>
                    <div className="flex gap-1">
                        <button
                            onClick={fetchChannels}
                            title="Refresh"
                            className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors"
                        >
                            <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                            onClick={newChannel}
                            className="p-1.5 hover:bg-zinc-800 text-white transition-colors border border-dashed border-zinc-600 hover:border-white"
                            title="New Channel"
                        >
                            <Plus className="h-4 w-4" />
                        </button>
                    </div>
                </div>

                <div className="space-y-2 flex-1 overflow-y-auto modern-scrollbar">
                    {channels.length === 0 && (
                        <div className="p-6 text-center text-zinc-600 text-xs border border-dashed border-zinc-800">
                            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-20" />
                            No channels configured yet.<br />Click + to add one.
                        </div>
                    )}
                    {channels.map(ch => {
                        const pm = PLATFORMS.find(p => p.id === ch.platform);
                        const isSelected = selectedId === ch.id;
                        return (
                            <div
                                key={ch.id}
                                onClick={() => selectChannel(ch)}
                                className={`p-3 border cursor-pointer transition-all group relative
                                    ${isSelected ? 'bg-zinc-900 border-white' : 'bg-black border-zinc-800 hover:border-zinc-600'}`}
                            >
                                <div className="flex items-center gap-3">
                                    <div className={`h-8 w-8 flex-shrink-0 flex items-center justify-center border ${pm?.color ?? ''}`}>
                                        <img src={pm?.icon} alt={pm?.label} className="h-5 w-5 object-contain" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-xs font-bold text-white truncate">{ch.name}</div>
                                        <div className="text-[10px] text-zinc-500 truncate">
                                            {agents.find(a => a.id === ch.agent_id)?.name || ch.agent_id}
                                        </div>
                                    </div>
                                    {/* Status badge: hidden on hover */}
                                    <div className="group-hover:hidden flex-shrink-0">
                                        <StatusBadge status={ch.status} lastError={ch.last_error} />
                                    </div>
                                    {/* Quick actions: shown on hover */}
                                    <div className="hidden group-hover:flex gap-1 flex-shrink-0">
                                        <button
                                            onClick={e => { e.stopPropagation(); toggleEnable(ch); }}
                                            className={`p-1 transition-colors ${ch.status === 'running' ? 'text-orange-400 hover:text-orange-300' : 'text-green-400 hover:text-green-300'}`}
                                            title={ch.status === 'running' ? 'Stop' : 'Start'}
                                        >
                                            {ch.status === 'running' ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                                        </button>
                                        <button
                                            onClick={e => { e.stopPropagation(); setConfirmDeleteId(ch.id || null); }}
                                            className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                                        >
                                            <Trash className="h-3 w-3" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ── Right: Editor ──────────────────────────────────────── */}
            <div className="md:col-span-8 pl-4">
                {draft ? (
                    <div className="space-y-6">
                        {/* Header */}
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-white flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full bg-purple-500" />
                                {selectedId ? `EDITING: ${draft.name.toUpperCase() || 'CHANNEL'}` : 'NEW CHANNEL'}
                            </h3>
                            <div className="flex gap-2">
                                {selectedId && (
                                    <button
                                        onClick={testChannel}
                                        disabled={testing}
                                        className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-bold transition-colors disabled:opacity-50"
                                    >
                                        {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <FlaskConical className="h-3 w-3" />}
                                        TEST
                                    </button>
                                )}
                                <button
                                    onClick={saveAndConnect}
                                    disabled={saving}
                                    className="flex items-center gap-2 px-4 py-1.5 bg-white text-black text-xs font-bold hover:bg-zinc-200 disabled:opacity-50"
                                >
                                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                                    SAVE & CONNECT
                                </button>
                            </div>
                        </div>

                        {/* Platform picker */}
                        <div className="space-y-2">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Platform</label>
                            <div className="grid grid-cols-5 gap-2">
                                {PLATFORMS.map(p => (
                                    <button
                                        key={p.id}
                                        onClick={() => setDraft({ ...EMPTY_CHANNEL, platform: p.id, name: draft.name, agent_id: draft.agent_id })}
                                        className={`flex flex-col items-center gap-1 p-3 border text-xs font-bold transition-all
                                            ${draft.platform === p.id
                                                ? `${p.color} border-current`
                                                : 'bg-black border-zinc-800 text-zinc-500 hover:border-zinc-600'}`}
                                    >
                                        <img src={p.icon} alt={p.label} className="h-6 w-6 object-contain" />
                                        {p.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Common fields */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <label className="text-[10px] font-bold text-zinc-500 uppercase">Channel Name</label>
                                <input
                                    type="text"
                                    value={draft.name}
                                    onChange={e => setDraft({ ...draft, name: e.target.value })}
                                    placeholder="e.g. Support Bot"
                                    className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                                />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] font-bold text-zinc-500 uppercase">Bound Agent</label>
                                <select
                                    value={draft.agent_id}
                                    onChange={e => setDraft({ ...draft, agent_id: e.target.value })}
                                    className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                                >
                                    <option value="">Select an agent…</option>
                                    {agents.map(a => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="flex items-start gap-4 p-3 bg-zinc-950 border border-zinc-800">
                            <input
                                id="multi-agent-toggle"
                                type="checkbox"
                                checked={draft.multi_agent_mode}
                                onChange={e => setDraft({ ...draft, multi_agent_mode: e.target.checked })}
                                className="mt-1 accent-purple-500"
                            />
                            <div className="flex-1">
                                <label htmlFor="multi-agent-toggle" className="text-xs font-bold text-white cursor-pointer block leading-tight">
                                    Multi-Agent Mode
                                </label>
                                <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                                    When enabled, users can switch agents mid-chat using <code className="bg-zinc-800 px-1">/agent &lt;name&gt;</code> and list them with <code className="bg-zinc-800 px-1">/agents</code>.
                                    The channel's bound agent is the default.
                                </p>
                            </div>
                        </div>

                        {/* Platform-specific credentials */}
                        <div className="space-y-3">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Credentials — {platformMeta?.label}</label>

                            {/* WhatsApp special UI */}
                            {draft.platform === 'whatsapp' ? (
                                <div className="space-y-4">
                                    {/* Mode selector */}
                                    <div className="grid grid-cols-2 gap-3">
                                        {[
                                            { v: 'meta_api', label: '🏢 Business (Meta API)', desc: 'Official. Requires Meta Business account + verified number.' },
                                            { v: 'unofficial', label: '🛠 Unofficial (Playwright)', desc: 'No business account. Uses WhatsApp Web automation.' },
                                        ].map(opt => (
                                            <button
                                                key={opt.v}
                                                onClick={() => { setWaMode(opt.v as any); setWaRiskAck(false); }}
                                                className={`p-3 border text-left text-xs transition-all
                                                    ${waMode === opt.v ? 'bg-zinc-900 border-white' : 'bg-black border-zinc-800 hover:border-zinc-600'}`}
                                            >
                                                <div className="font-bold text-white">{opt.label}</div>
                                                <div className="text-zinc-500 mt-1">{opt.desc}</div>
                                            </button>
                                        ))}
                                    </div>

                                    {waMode === 'meta_api' && (
                                        <div className="space-y-3">
                                            {[
                                                { key: 'phone_number_id', label: 'Phone Number ID', placeholder: '123456789012345', secret: false },
                                                { key: 'access_token', label: 'Access Token', placeholder: 'EAA...', secret: true },
                                                { key: 'verify_token', label: 'Verify Token (your choice)', placeholder: 'synapse_verify', secret: false,
                                                  note: 'Used to verify Meta webhook. Set the same value in your Meta App settings.' },
                                            ].map(f => (
                                                <div key={f.key} className="space-y-1">
                                                    <label className="text-[10px] font-bold text-zinc-500 uppercase">{f.label}</label>
                                                    <input
                                                        type={f.secret ? 'password' : 'text'}
                                                        value={draft.credentials[f.key] || ''}
                                                        onChange={e => updateCred(f.key, e.target.value)}
                                                        placeholder={f.placeholder}
                                                        className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none font-mono"
                                                    />
                                                    {f.note && <p className="text-[9px] text-zinc-600">{f.note}</p>}
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {waMode === 'unofficial' && (
                                        <div className="space-y-3">
                                            <div className="flex gap-2 p-3 bg-amber-950/30 border border-amber-800/50">
                                                <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
                                                <div className="text-[10px] text-amber-300 space-y-1">
                                                    <p className="font-bold">⚠️ Unofficial Approach — Use at Your Own Risk</p>
                                                    <p>This mode uses Playwright to drive WhatsApp Web in a browser window. It requires scanning a QR code. It may:</p>
                                                    <ul className="list-disc pl-4 space-y-0.5">
                                                        <li>Violate WhatsApp's Terms of Service</li>
                                                        <li>Break when WhatsApp updates their web app</li>
                                                        <li>Result in your number being temporarily banned</li>
                                                    </ul>
                                                    <p>We recommend using the official Meta Business path instead.</p>
                                                </div>
                                            </div>
                                            <div className="flex items-start gap-3 p-3 bg-zinc-950 border border-zinc-800">
                                                <input
                                                    id="wa-risk-ack"
                                                    type="checkbox"
                                                    checked={waRiskAck}
                                                    onChange={e => setWaRiskAck(e.target.checked)}
                                                    className="mt-1 accent-amber-500"
                                                />
                                                <label htmlFor="wa-risk-ack" className="text-xs text-zinc-300 cursor-pointer leading-tight">
                                                    I understand the risks and accept responsibility for using the unofficial path.
                                                </label>
                                            </div>
                                            {waRiskAck && (
                                                <div className="p-3 bg-zinc-950 border border-zinc-700 text-[10px] text-zinc-400 space-y-1">
                                                    <p>After saving & connecting, Synapse will open WhatsApp Web in a Chromium browser window.</p>
                                                    <p>Scan the QR code shown in the browser to authenticate. The session is saved and persists across restarts.</p>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                /* Standard credential fields */
                                <div className="space-y-3">
                                    {CREDENTIAL_FIELDS[draft.platform]?.map(f => (
                                        <div key={f.key} className="space-y-1">
                                            <label className="text-[10px] font-bold text-zinc-500 uppercase">{f.label}</label>
                                            <input
                                                type={f.secret ? 'password' : 'text'}
                                                value={draft.credentials[f.key] || ''}
                                                onChange={e => updateCred(f.key, e.target.value)}
                                                placeholder={f.placeholder}
                                                className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none font-mono"
                                            />
                                            {f.note && (
                                                <p className="text-[9px] text-zinc-600 flex items-center gap-1">
                                                    <Info className="h-2.5 w-2.5" /> {f.note}
                                                </p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Setup Guide accordion */}
                        <div className="border border-zinc-800">
                            <button
                                onClick={() => setGuideOpen(g => !g)}
                                className="w-full flex items-center justify-between px-4 py-3 text-xs font-bold text-zinc-400 hover:text-white hover:bg-zinc-900/50 transition-colors"
                            >
                                <span>📖 Setup Guide — {guide.title}</span>
                                {guideOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            </button>
                            {guideOpen && (
                                <div className="px-4 pb-4 space-y-2 bg-zinc-950/50">
                                    <ol className="space-y-2">
                                        {guide.steps.map((s, i) => (
                                            <li key={i} className="flex gap-2 text-[10px] text-zinc-400">
                                                <span className="text-zinc-600 font-bold flex-shrink-0">{s.startsWith('---') ? '' : `${i + 1}.`}</span>
                                                <span className={s.startsWith('---') ? 'text-zinc-700 border-t border-zinc-800 w-full pt-1' : ''}>{s}</span>
                                            </li>
                                        ))}
                                    </ol>
                                </div>
                            )}
                        </div>

                        {/* Error display */}
                        {draft.last_error && (
                            <div className="flex gap-2 p-3 bg-red-950/30 border border-red-900/50">
                                <XCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                                <div>
                                    <p className="text-xs font-bold text-red-400">Last Error</p>
                                    <p className="text-[10px] text-red-300 mt-0.5 font-mono">{draft.last_error}</p>
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="h-full flex flex-col items-center justify-center text-zinc-600 space-y-4 py-20">
                        <MessageSquare className="h-12 w-12 opacity-20" />
                        <p className="text-sm">Select a channel or create a new one.</p>
                    </div>
                )}
            </div>

            <ConfirmationModal
                isOpen={!!confirmDeleteId}
                title="Delete Channel"
                message="Are you sure you want to delete this messaging channel? This will permanently remove its configuration and stop it if it is running."
                onConfirm={() => {
                    if (confirmDeleteId) deleteChannel(confirmDeleteId);
                    setConfirmDeleteId(null);
                }}
                onClose={() => setConfirmDeleteId(null)}
            />
        </div>
    );
};
