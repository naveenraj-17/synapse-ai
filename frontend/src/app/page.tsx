'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Bot, User, Settings, Terminal, Sun, Moon, Plus, ChevronDown, ChevronRight, Zap, GitBranch, CheckCircle2, AlertCircle, History, RefreshCw, Clock, Trash2, X, Paperclip, ImageIcon } from 'lucide-react';

import { useRouter } from 'next/navigation';
import { CollectDataForm } from '@/components/CollectDataForm';

import { renderTextContent, cn } from '@/lib/utils';
import { Message, OrchMsgType, SystemStatus } from '@/types';

// ─── LLM Thought Collapsible ────────────────────────────────────────────────
function ThoughtCollapsible({ thoughts, stepName }: { thoughts: string[]; stepName?: string }) {
  const [open, setOpen] = useState(false);

  // Filter out pure JSON tool calls — only show natural-language reasoning
  const naturalThoughts = thoughts.filter(t => {
    const trimmed = t.trim();
    if (!trimmed) return false;
    // If it starts with { and looks like JSON, it's a tool call — skip unless short enough to be partly text
    if (trimmed.startsWith('{')) {
      try { JSON.parse(trimmed); return false; } catch { /* not pure JSON */ }
    }
    return true;
  });

  if (naturalThoughts.length === 0) return null;

  return (
    <div className="mt-2 border border-zinc-800 rounded-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] font-mono text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/40 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span className="uppercase tracking-wider">
          💭 Reasoning {stepName ? `· ${stepName}` : ''} ({naturalThoughts.length} turn{naturalThoughts.length > 1 ? 's' : ''})
        </span>
      </button>
      {open && (
        <div className="border-t border-zinc-800 bg-zinc-950/60 divide-y divide-zinc-900">
          {naturalThoughts.map((t, i) => (
            <div key={i} className="px-3 py-2 text-[12px] text-zinc-400 font-mono whitespace-pre-wrap leading-5">
              {naturalThoughts.length > 1 && (
                <span className="text-zinc-600 text-[10px] mr-2">Turn {i + 1}</span>
              )}
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Orchestration Step Divider ──────────────────────────────────────────────
function StepDivider({ stepName, stepType }: { stepName: string; stepType?: string }) {
  const typeIcon: Record<string, string> = {
    agent: '🤖', evaluator: '🔀', parallel: '⚡', merge: '🔗',
    loop: '🔄', human: '👤', transform: '⚙️', end: '🏁',
  };
  const icon = typeIcon[stepType || ''] ?? '▶';
  return (
    <div className="flex items-center gap-3 my-1 px-1">
      <div className="h-px flex-1 bg-gradient-to-r from-transparent to-zinc-800" />
      <div className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest text-zinc-500 shrink-0">
        <span>{icon}</span>
        <span>{stepName}</span>
        {stepType && <span className="text-zinc-700">· {stepType}</span>}
      </div>
      <div className="h-px flex-1 bg-gradient-to-l from-transparent to-zinc-800" />
    </div>
  );
}

// ─── Orchestration Info Banner ───────────────────────────────────────────────
function OrchBanner({ content, variant }: { content: string; variant: 'start' | 'complete' | 'error' }) {
  const styles: Record<string, string> = {
    start: 'border-purple-900/50 bg-purple-950/20 text-purple-400',
    complete: 'border-emerald-900/50 bg-emerald-950/20 text-emerald-400',
    error: 'border-red-900/50 bg-red-950/20 text-red-400',
  };
  return (
    <div className="flex justify-center my-2">
      <div className={cn('border px-5 py-1.5 text-[11px] font-mono uppercase tracking-widest rounded-sm', styles[variant])}>
        {content}
      </div>
    </div>
  );
}

// ─── Sub-agent Result Bubble ─────────────────────────────────────────────────
function AgentStepResult({ msg, onCollectDataSubmit }: {
  msg: Message;
  onCollectDataSubmit: (values: Record<string, unknown>) => void;
}) {
  return (
    <div className="flex gap-3 max-w-4xl">
      <div className="h-7 w-7 shrink-0 flex items-center justify-center border border-purple-800/50 bg-purple-950/30 text-purple-400 mt-1 rounded-sm">
        <Bot className="h-3.5 w-3.5" />
      </div>
      <div className="flex flex-col flex-1 min-w-0 gap-2">
        {msg.stepName && (
          <div className="text-[10px] uppercase tracking-widest text-purple-500/70 font-mono">
            {msg.stepName}
          </div>
        )}
        <div className="p-3 text-[14px] leading-7 border border-purple-900/30 bg-purple-950/10 relative font-sans rounded-sm">
          <div className="prose prose-invert max-w-none text-zinc-200 font-normal">
            {renderTextContent(msg.content)}
          </div>
        </div>
        {/* Thoughts */}
        {msg.thoughts && msg.thoughts.length > 0 && (
          <ThoughtCollapsible thoughts={msg.thoughts} stepName={msg.stepName} />
        )}
        {/* Intent-based UI */}
        <div className="w-full pl-1">
          {msg.intent === 'collect_data' && msg.data && (
            <CollectDataForm data={msg.data} onSubmit={onCollectDataSubmit} />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Types ───────────────────────────────────────────────────────────────────
type SessionSummary = {
  session_id: string;
  agent_id: string;
  last_response: string | null;
  last_updated: string | null;
  turn_count: number;
  first_user_message: string | null;
};

type SessionTurn = {
  user: string;
  assistant: string;
  tools: string[];
  timestamp: string;
};

function formatRelativeTime(iso: string | null): string {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Home() {
  const [sessionId, setSessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('synapseSessionId') || (() => {
        const c: any = (globalThis as any).crypto;
        return c?.randomUUID?.() ?? `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
      })();
    }
    const c: any = (globalThis as any).crypto;
    return c?.randomUUID?.() ?? `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  });

  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'System Internal v1.0. Ready for input.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [agentName, setAgentName] = useState('Loading...');
  const router = useRouter();
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [streamingActivity, setStreamingActivity] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Attached images (max 5)
  const [attachedImages, setAttachedImages] = useState<{ preview: string; base64: string }[]>([]);

  // Accumulate LLM thoughts per active step during streaming
  const pendingThoughtsRef = useRef<string[]>([]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Save current session to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('synapseSessionId', sessionId);
      if (currentAgentId) localStorage.setItem('synapseAgentId', currentAgentId);
    }
  }, [sessionId, currentAgentId]);

  // Restore persisted theme AFTER hydration (avoids SSR className mismatch)
  useEffect(() => {
    const saved = localStorage.getItem('synapseTheme') as 'dark' | 'light' | null;
    if (saved) setTheme(saved);
  }, []);



  // Fetch sessions list
  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await fetch('/api/sessions');
      if (res.ok) setSessions(await res.json());
    } catch (e) { console.error('[Sessions] fetch error', e); }
    finally { setSessionsLoading(false); }
  }, []);

  // Restore a session into the chat UI
  const restoreSession = useCallback(async (sid: string, agentId: string | null) => {
    try {
      const url = `/api/sessions/${sid}/history${agentId ? `?agent_id=${agentId}` : ''}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      const turns: SessionTurn[] = data.turns || [];
      if (turns.length === 0) return;
      const restored: Message[] = [{ role: 'assistant', content: 'System Internal v1.0. Ready for input.' }];
      for (const t of turns) {
        restored.push({ role: 'user', content: t.user });
        restored.push({ role: 'assistant', content: t.assistant });
      }
      setMessages(restored);
      setSessionId(sid);
      if (agentId) setCurrentAgentId(agentId);
    } catch (e) { console.error('[Sessions] restore error', e); }
  }, []);

  // Helper to refresh status
  const refreshSystemStatus = () => {
    fetch('/api/status').then(r => r.json()).then(d => {
      setSystemStatus(d);
      // Sync agent name with active agent from status to fix initial render mismatch
      if (d.active_agent_id && d.agents && d.agents[d.active_agent_id]) {
        const info = d.agents[d.active_agent_id];
        const name = typeof info === 'string' ? d.active_agent_id : info.name;
        setAgentName(name);
        setCurrentAgentId(d.active_agent_id);
      }
    }).catch(console.error);
  };

  // Initialize Application State (Replaces Initial Data Fetch & Auto-Restore)
  useEffect(() => {
    // 1. Get Agent Name
    fetch('/api/settings')
      .then(r => r.json())
      .then(d => setAgentName(d.agent_name || 'System Agent'))
      .catch(() => setAgentName('Offline'));
      
    // 2. Auto-restore session and sync agent to backend sequentially
    const initSessionAndAgent = async () => {
      const savedSession = typeof window !== 'undefined' ? localStorage.getItem('synapseSessionId') : null;
      const savedAgent = typeof window !== 'undefined' ? localStorage.getItem('synapseAgentId') : null;

      if (savedSession) {
        // Await the restoration of the chat history
        await restoreSession(savedSession, savedAgent);
        
        if (savedAgent) {
          try {
            // Force the backend to align with the restored session's agent
            await fetch('/api/agents/active', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ agent_id: savedAgent }),
            });
          } catch (e) {
            console.error('Failed to sync active agent on load', e);
          }
        }
      }
      
      // 4. Get Status (after session and agent sync)
      refreshSystemStatus();
    };

    initSessionAndAgent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNewChat = () => {
    const c: any = (globalThis as any).crypto;
    const newSessionId = c?.randomUUID?.() ?? `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    setSessionId(newSessionId);
    setMessages([{ role: 'assistant', content: 'System Internal v1.0. Ready for input.' }]);
    setStreamingActivity(null);
  };

  const handleRefresh = () => {
    refreshSystemStatus();
    if (isHistoryOpen) fetchSessions();
  };

  const handleOpenHistory = () => {
    setIsHistoryOpen(true);
    fetchSessions();
  };

  const handleSelectSession = async (s: SessionSummary) => {
    setIsHistoryOpen(false);
    await restoreSession(s.session_id, s.agent_id);
    // Switch agent if needed
    if (s.agent_id && s.agent_id !== currentAgentId) {
      try {
        await fetch('/api/agents/active', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_id: s.agent_id }),
        });
        refreshSystemStatus();
      } catch { }
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, s: SessionSummary) => {
    e.stopPropagation();
    await fetch(`/api/sessions/${s.session_id}?agent_id=${s.agent_id}`, { method: 'DELETE' });
    setSessions(prev => prev.filter(x => x.session_id !== s.session_id));
  };

  const handleSwitchAgent = async (agentId: string) => {
    try {
      const res = await fetch('/api/agents/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId })
      });
      if (res.ok) {
        // Refresh status immediately
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        setSystemStatus(statusData);
        const name = statusData.agents[agentId]?.name || agentId;
        if (statusData.agents[agentId]) {
          setAgentName(name);
        }
        setCurrentAgentId(agentId);

        // Generate new session for the new agent — isolates context
        const c: any = (globalThis as any).crypto;
        const newSessionId = c?.randomUUID?.() ?? `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
        setSessionId(newSessionId);

        // Clear chat messages for clean agent context
        setMessages([{ role: 'assistant', content: `System: Switched to ${name}. Ready.` }]);
      }
    } catch (e) {
      console.error("Failed to switch agent", e);
    }
  };



  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && attachedImages.length === 0) || isLoading) return;

    const userMessage = input.trim() || (attachedImages.length > 0 ? '[Images attached]' : '');
    const imagesToSend = attachedImages.map(img => img.base64);
    setInput('');
    setAttachedImages([]);
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setMessages(prev => [...prev, { role: 'user', content: userMessage, images: imagesToSend.length > 0 ? imagesToSend : undefined }]);

    await processMessage(userMessage, imagesToSend);
  };

  const handleCollectDataSubmit = async (values: Record<string, any>) => {
    // Format the response based on whether it's a single field or multiple fields
    const keys = Object.keys(values);

    let userMessage: string;
    if (keys.length === 1) {
      // Single field: just send the value
      const value = values[keys[0]];
      userMessage = Array.isArray(value) ? value.join(', ') : String(value);
    } else {
      // Multiple fields: format as "Field1: value1, Field2: value2"
      userMessage = keys
        .map(key => {
          const value = values[key];
          const displayValue = Array.isArray(value) ? value.join(', ') : value;
          return `${key}: ${displayValue}`;
        })
        .join(', ');
    }

    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    await processMessage(userMessage);
  };

  // Refactor duplicate fetch logic into helper
  const processMessage = async (content: string, images?: string[]) => {
    setIsLoading(true);
    setStreamingActivity(null);
    setIsThinking(false);
    pendingThoughtsRef.current = [];

    // Try SSE streaming first
    try {
      await processMessageSSE(content, images);
    } catch (sseError) {
      console.error('[SSE] SSE failed, falling back to HTTP:', sseError);
      // Fallback to HTTP
      await processMessageHTTP(content, images);
    } finally {
      setIsLoading(false);
      setStreamingActivity(null);
      setIsThinking(false);
      pendingThoughtsRef.current = [];
    }
  };

  // SSE Streaming implementation
  const processMessageSSE = async (content: string, images?: string[]) => {
    return new Promise<void>((resolve, reject) => {
      // Track state local to this SSE stream
      let currentStepThoughts: string[] = [];
      let currentOrchStepId: string | null = null;

      console.log('[SSE] Attempting SSE connection to /api/chat/stream');
      fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: sessionId, agent_id: currentAgentId, images: images || [] }),
      })
        .then(async (response) => {
          if (!response.ok) {
            throw new Error(`SSE request failed: ${response.status}`);
          }

          const reader = response.body?.getReader();
          const decoder = new TextDecoder();

          if (!reader) {
            throw new Error('No reader available for SSE');
          }

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
                  console.log('[SSE Event]', data.type, data);

                  switch (data.type) {

                    // ── Standard events ──────────────────────────────────────────
                    case 'status':
                      setStreamingActivity(data.message);
                      setIsThinking(false);
                      break;

                    case 'thinking':
                      setIsThinking(true);
                      break;

                    case 'tool_execution': {
                      const toolDisplayName = data.tool_name
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (l: string) => l.toUpperCase());
                      const stepLabel = data.step_name ? ` · ${data.step_name}` : '';
                      setStreamingActivity(`🔧 ${toolDisplayName}${stepLabel}`);
                      setIsThinking(false);
                      break;
                    }

                    case 'tool_result':
                      setStreamingActivity(`✓ Processing results`);
                      setIsThinking(false);
                      break;

                    case 'llm_thought':
                      // Accumulate thoughts for the current step
                      if (data.orch_step_id) {
                        // Inside orchestration — reset if new step started
                        if (data.orch_step_id !== currentOrchStepId) {
                          currentStepThoughts = [];
                          currentOrchStepId = data.orch_step_id;
                        }
                        currentStepThoughts = [...currentStepThoughts, data.thought];
                      } else {
                        // Single-agent flow — accumulate in pending ref
                        pendingThoughtsRef.current = [...pendingThoughtsRef.current, data.thought];
                      }
                      setIsThinking(true);
                      break;

                    case 'response':
                      // Final response — clear pending thoughts (they'll be shown in the message)
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: data.content,
                        intent: data.intent,
                        data: data.data,
                        tool: data.tool_name,
                        thoughts: [...pendingThoughtsRef.current],
                      }]);
                      pendingThoughtsRef.current = [];
                      break;

                    // ── Orchestration lifecycle ──────────────────────────────────
                    case 'orchestration_start':
                      setStreamingActivity(`🚀 Starting orchestration`);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: `🚀 ${data.orchestration_name || 'Orchestration'} started`,
                        msgType: 'orchestration_start',
                      }]);
                      break;

                    case 'step_start':
                      // Reset thoughts for this new step
                      currentStepThoughts = [];
                      currentOrchStepId = data.orch_step_id;
                      setStreamingActivity(`▶ ${data.step_name || 'Step'}`);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: data.step_name || 'Step',
                        msgType: 'step_start',
                        stepName: data.step_name,
                        stepType: data.step_type,
                        orchStepId: data.orch_step_id,
                      }]);
                      break;

                    case 'agent_step_result':
                      // Sub-agent completed — add as purple-accented bubble with thoughts
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: data.content,
                        intent: data.intent,
                        data: data.data,
                        tool: data.tool_name,
                        msgType: 'agent_step_result',
                        stepName: data.step_name,
                        orchStepId: data.orch_step_id,
                        thoughts: [...currentStepThoughts],
                      }]);
                      // Reset for next step
                      currentStepThoughts = [];
                      break;

                    case 'step_complete':
                      setStreamingActivity(`✓ ${data.step_name || 'Step'} complete`);
                      break;

                    case 'step_error':
                      setStreamingActivity(`✗ Step failed`);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: `❌ Step failed: ${data.error || 'Unknown error'}`,
                        msgType: 'orchestration_start', // reuse error styling via variant
                      }]);
                      break;

                    case 'orchestration_complete':
                      setStreamingActivity(`Orchestration ${data.status}`);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: `✅ Orchestration ${data.status || 'complete'}`,
                        msgType: 'orchestration_complete',
                      }]);
                      break;

                    case 'orchestration_error':
                      setStreamingActivity(`Orchestration error`);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: `❌ Orchestration error: ${data.error || 'Unknown error'}`,
                        msgType: 'orchestration_complete',
                      }]);
                      break;

                    case 'human_input_required':
                      setStreamingActivity(null);
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: data.prompt || 'Please provide input to continue.',
                        msgType: 'human_input_required',
                        data: {
                          fields: data.fields,
                          run_id: data.run_id,
                          agent_context: data.agent_context,
                          channel_id: data.channel_id,
                        },
                      }]);
                      break;

                    // ── Parallel / loop / routing info ───────────────────────────
                    case 'routing_decision':
                      setStreamingActivity(`🔀 Route: ${data.decision || data.tool_name}`);
                      break;

                    case 'loop_iteration':
                      setStreamingActivity(`🔄 Loop iteration ${data.iteration}/${data.total}`);
                      break;

                    case 'parallel_start':
                      setStreamingActivity(`⚡ Running ${data.branch_count} parallel branches`);
                      break;

                    case 'branch_start':
                      setStreamingActivity(`⚡ Branch ${(data.branch_index ?? 0) + 1}/${data.branch_count}`);
                      break;

                    case 'merge_complete':
                      setStreamingActivity(`🔗 Merged ${data.input_count} results`);
                      break;

                    case 'done':
                      resolve();
                      return;

                    case 'error':
                      reject(new Error(data.message));
                      return;
                  }
                } catch (e) {
                  console.error('Failed to parse SSE event:', e);
                }
              }
            }
          }

          resolve();
        })
        .catch((err) => {
          reject(err);
        });
    });
  };

  // HTTP fallback implementation (original logic)
  const processMessageHTTP = async (content: string, images?: string[]) => {
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: sessionId, images: images || [] }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        intent: data.intent,
        data: data.data
      }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: "Error communicating with agent." }]);
    }
  };

  // ─── Rendering helpers ─────────────────────────────────────────────────────

  const renderMessage = (msg: Message, idx: number) => {
    // ── Orchestration start / complete banners ──
    if (msg.msgType === 'orchestration_start') {
      return (
        <div key={idx}>
          <OrchBanner content={msg.content} variant="start" />
        </div>
      );
    }
    if (msg.msgType === 'orchestration_complete') {
      const isError = msg.content.startsWith('❌');
      return (
        <div key={idx}>
          <OrchBanner content={msg.content} variant={isError ? 'error' : 'complete'} />
        </div>
      );
    }

    // ── Step divider line ──
    if (msg.msgType === 'step_start') {
      return (
        <div key={idx}>
          <StepDivider stepName={msg.stepName || msg.content} stepType={msg.stepType} />
        </div>
      );
    }

    // ── Sub-agent result (purple accent bubble) ──
    if (msg.msgType === 'agent_step_result') {
      return (
        <AgentStepResult
          key={idx}
          msg={msg}
          onCollectDataSubmit={handleCollectDataSubmit}
        />
      );
    }

    // ── Human input required ──
    if (msg.msgType === 'human_input_required') {
      return (
        <div key={idx} className="flex gap-4 max-w-4xl">
          <div className="h-8 w-8 shrink-0 flex items-center justify-center border border-amber-700/50 bg-amber-950/30 text-amber-400">
            <User className="h-4 w-4" />
          </div>
          <div className="flex flex-col flex-1 min-w-0 gap-3">
            <div className="p-4 text-[15px] leading-7 border border-amber-900/40 bg-amber-950/10 relative font-sans">
              <div className="absolute -top-3 left-2 bg-zinc-950 border border-amber-900/50 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-500 font-mono">
                Human Input Required
              </div>
              {msg.data?.agent_context && (
                <div className="mb-3 p-3 bg-zinc-900/60 border border-zinc-800 text-xs text-zinc-400 font-mono whitespace-pre-wrap max-h-40 overflow-auto rounded-sm">
                  {msg.data.agent_context}
                </div>
              )}
              <div className="prose prose-invert max-w-none text-zinc-100 font-normal mb-4">
                {renderTextContent(msg.content)}
              </div>
              {msg.data?.fields && (
                <CollectDataForm data={msg.data} onSubmit={handleCollectDataSubmit} />
              )}
              {msg.data?.channel_id && (
                <div className="mt-2 text-[11px] text-zinc-500 font-mono">
                  📲 Notification sent to messaging channel
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    // ── Regular user / assistant message ──
    return (
      <div key={idx} className={cn(
        "flex gap-4",
        msg.role === 'assistant' ? "max-w-4xl" : "max-w-3xl",
        msg.role === 'user' ? "ml-auto flex-row-reverse" : ""
      )}>
        <div className={cn(
          "h-8 w-8 shrink-0 flex items-center justify-center border",
          msg.role === 'user' ? "bg-white border-white text-black" : "bg-black border-zinc-700 text-zinc-400"
        )}>
          {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>

        <div className="flex flex-col flex-1 min-w-0 gap-2">
          <div className={cn(
            "p-4 text-[15px] leading-7 border relative font-sans",
            msg.role === 'user'
              ? "bg-zinc-900 border-zinc-800 text-zinc-100 self-end max-w-[80%]"
              : "bg-zinc-900/50 border-zinc-800 text-zinc-100 self-start max-w-full"
          )}>
            {/* Intent Indicator for Assistant */}
            {msg.role === 'assistant' && msg.intent && (
              <div className="absolute -top-3 left-2 bg-zinc-950 border border-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-zinc-400 font-mono">
                {msg.intent.replaceAll('_', ' ')} Operation
              </div>
            )}

            {/* Content */}
            <div className="prose prose-invert max-w-none text-zinc-100 font-normal">
              {renderTextContent(msg.content)}
            </div>

            {/* Attached Images */}
            {msg.images && msg.images.length > 0 && (
              <div className="flex flex-wrap gap-3 mt-4">
                {msg.images.map((img, imgIdx) => (
                  <div key={imgIdx} className="relative group">
                    <img
                      src={img}
                      alt={`Attached ${imgIdx + 1}`}
                      className="h-[4.5rem] w-[4.5rem] object-cover border border-zinc-700/60 rounded-xl cursor-pointer hover:border-zinc-400 hover:scale-[1.03] hover:shadow-lg transition-all"
                      onClick={() => window.open(img, '_blank')}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* LLM Thoughts for regular responses */}
          {msg.role === 'assistant' && msg.thoughts && msg.thoughts.length > 0 && (
            <ThoughtCollapsible thoughts={msg.thoughts} />
          )}

          {/* Dynamic UI based on Intent - Rendered Outside Bubble */}
          {msg.role === 'assistant' && (
            <div className="w-full mt-2 pl-1">
              {msg.intent === 'render_local_file' && (
                <div className="mt-4 p-4 bg-zinc-950 border border-zinc-800 font-mono text-xs whitespace-pre-wrap max-h-96 overflow-auto text-zinc-300">
                  {msg.data.content}
                </div>
              )}
              {msg.intent === 'collect_data' && msg.data && (
                <CollectDataForm data={msg.data} onSubmit={handleCollectDataSubmit} />
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <main className={cn("flex h-screen bg-black text-white font-mono overflow-hidden", theme === 'light' ? 'light-mode' : '')}>

      {/* ── History Drawer ────────────────────────────────────────────────── */}
      {isHistoryOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-pointer"
            onClick={() => setIsHistoryOpen(false)}
          />
          {/* Panel */}
          <div className="relative z-10 w-80 max-w-full h-full bg-zinc-950 border-r border-zinc-800 flex flex-col shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-zinc-400" />
                <span className="text-xs font-bold uppercase tracking-widest text-zinc-300">Chat History</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={fetchSessions}
                  disabled={sessionsLoading}
                  className="p-1.5 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors"
                  title="Refresh sessions"
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", sessionsLoading && "animate-spin")} />
                </button>
                <button
                  onClick={() => setIsHistoryOpen(false)}
                  className="p-1.5 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Session List */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {sessionsLoading && sessions.length === 0 && (
                <div className="flex items-center justify-center py-10 text-zinc-500 text-xs">Loading...</div>
              )}
              {!sessionsLoading && sessions.length === 0 && (
                <div className="flex flex-col items-center justify-center py-10 gap-2">
                  <Clock className="h-8 w-8 text-zinc-700" />
                  <span className="text-xs text-zinc-500">No chat history yet</span>
                </div>
              )}
              {sessions.map(s => (
                <div
                  key={`${s.agent_id}_${s.session_id}`}
                  onClick={() => handleSelectSession(s)}
                  className={cn(
                    "group relative px-4 py-3 border-b border-zinc-900 cursor-pointer hover:bg-zinc-900/60 transition-colors",
                    s.session_id === sessionId && "bg-zinc-900"
                  )}
                >
                  {/* Active indicator */}
                  {s.session_id === sessionId && (
                    <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-white" />
                  )}
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono truncate">
                      {s.agent_id || 'default'}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-[10px] text-zinc-600 font-mono">
                        {formatRelativeTime(s.last_updated)}
                      </span>
                      <button
                        onClick={(e) => handleDeleteSession(e, s)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 text-zinc-600 transition-all"
                        title="Delete session"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                  <p className="text-[12px] text-zinc-300 leading-5 line-clamp-2">
                    {s.first_user_message || '(no messages)'}
                  </p>
                  {s.last_response && (
                    <p className="text-[11px] text-zinc-500 mt-1 truncate">
                      ↩ {s.last_response.slice(0, 80)}{s.last_response.length > 80 ? '…' : ''}
                    </p>
                  )}
                  <div className="text-[10px] text-zinc-700 mt-1 font-mono">
                    {s.turn_count} turn{s.turn_count !== 1 ? 's' : ''}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer — new chat shortcut */}
            <div className="px-4 py-3 border-t border-zinc-800 shrink-0">
              <button
                onClick={() => { setIsHistoryOpen(false); handleNewChat(); }}
                className="w-full flex items-center justify-center gap-2 py-2 border border-zinc-700 hover:border-zinc-500 text-zinc-400 hover:text-white text-xs uppercase tracking-widest transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                New Chat
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col w-full border-x border-zinc-800 shadow-2xl relative">
        {/* Header */}
        <header className="h-14 border-b border-zinc-800 bg-zinc-950 px-6 shrink-0 z-10">
          <div className='w-full md:max-w-5xl mx-auto h-full flex items-center justify-between'>
            <div className="flex items-center gap-3 min-w-0">
              <div className="h-3 w-3 shrink-0 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_#22c55e]"></div>
              <h1 className="text-base font-bold tracking-widest uppercase text-zinc-100 flex items-center gap-2 min-w-0">
                <span
                  className="truncate max-w-[180px] md:max-w-[260px]"
                  title={agentName}
                >
                  {agentName}
                </span>
                <span className="text-zinc-500 shrink-0">-</span>
                <span className="text-zinc-400 shrink-0">Ask Anything</span>
              </h1>
            </div>
            <div className="flex items-center">
              {/* Mode & Model Info */}
              <div className="hidden md:flex items-center gap-4 text-xs text-zinc-400 uppercase tracking-wider border-r border-zinc-800 pr-4">
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400">Provider:</span>
                  <span className={cn("font-bold",
                    systemStatus?.provider === 'ollama' ? "text-green-400" :
                      systemStatus?.provider === 'gemini' ? "text-blue-400" :
                        systemStatus?.provider === 'anthropic' ? "text-amber-400" :
                          systemStatus?.provider === 'openai' ? "text-emerald-400" :
                            "text-purple-400"
                  )}>
                    {systemStatus?.provider ? systemStatus.provider.charAt(0).toUpperCase() + systemStatus.provider.slice(1) : 'Loading...'}
                  </span>
                </div>
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-zinc-400 shrink-0">Model:</span>
                  <span
                    className="text-zinc-200 truncate max-w-[120px] lg:max-w-[180px]"
                    title={systemStatus?.model || undefined}
                  >
                    {systemStatus?.model || 'Loading...'}
                  </span>
                </div>
              </div>

              {/* Status Indicators */}
              {/* Agents Hover Status */}
              <div className="group relative flex items-center gap-2 cursor-pointer border-r border-zinc-800 pl-4 pr-4 hover:bg-zinc-900 transition-colors">
                <span className="text-xs font-bold text-zinc-400 tracking-widest uppercase group-hover:text-zinc-200 transition-colors">AGENTS</span>

                {/* Dropdown on Hover */}
                <div className="absolute right-0 top-full mt-0 w-64 bg-zinc-950 border border-zinc-800 p-2 shadow-2xl opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all pointer-events-none group-hover:pointer-events-auto z-50">
                  <div className="space-y-1">
                    {systemStatus?.agents && Object.entries(systemStatus.agents).map(([id, info]) => {
                      const isActive = systemStatus.active_agent_id === id;
                      // Handle legacy string vs new object structure if backend update lags (safety)
                      const name = typeof info === 'string' ? id : info.name;
                      const status = typeof info === 'string' ? info : info.status;

                      return (
                        <button
                          key={id}
                          onClick={() => handleSwitchAgent(id)}
                          className={cn(
                            "nav-button w-full flex items-center justify-between px-3 py-2 text-xs uppercase tracking-wider text-left border border-transparent hover:border-zinc-700 transition-all",
                            isActive ? "bg-zinc-900 text-white border-zinc-800" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50"
                          )}>
                          <div className="flex items-center gap-2">
                            <div className={cn("h-1.5 w-1.5 rounded-full", status === 'online' ? "bg-green-500 shadow-[0_0_5px_#22c55e]" : "bg-red-500")}></div>
                            <span className="truncate max-w-[200px]">{name}</span>
                          </div>
                          {isActive && <div className="h-1.5 w-1.5 bg-white rounded-full animate-pulse"></div>}
                        </button>
                      );
                    })}
                    {(!systemStatus?.agents || Object.keys(systemStatus.agents).length === 0) && (
                      <div className="text-xs text-zinc-500 italic px-3 py-2">No agents detected.</div>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={handleNewChat}
                className="p-2 ml-2 hover:bg-zinc-900 rounded text-zinc-400 hover:text-white transition-colors"
                title="New Chat"
              >
                <Plus className="h-4 w-4" />
              </button>

              <button
                onClick={handleOpenHistory}
                className="p-2 hover:bg-zinc-900 rounded text-zinc-400 hover:text-white transition-colors"
                title="Chat History"
              >
                <History className="h-4 w-4" />
              </button>

              <button
                onClick={() => setTheme(prev => {
                  const next = prev === 'dark' ? 'light' : 'dark';
                  localStorage.setItem('synapseTheme', next);
                  return next;
                })}
                className="p-2 ml-2 hover:bg-zinc-900 rounded text-zinc-400 hover:text-white transition-colors"
                title={theme === 'dark' ? "Switch to Light Mode" : "Switch to Dark Mode"}
              >
                {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>

              <button
                onClick={() => router.push('/settings/general')}
                className="p-2 ml-2 hover:bg-zinc-900 rounded text-zinc-400 hover:text-white transition-colors"
              >
                <Settings className="h-4 w-4" />
              </button>
            </div>
          </div>

        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-6 scroll-smooth custom-scrollbar pb-32">
          <div className="w-full md:max-w-5xl mx-auto space-y-6">
            {messages.map((msg, idx) => renderMessage(msg, idx))}

            {/* Loading Indicator */}
            {isLoading && (
              <div className="flex gap-4 max-w-3xl items-start">
                {/* Spinning Bot Icon with Ring */}
                <div className="relative h-8 w-8 shrink-0 mt-0.5">
                  {/* Outer spinning ring */}
                  <div className="absolute inset-0 border-2 border-transparent border-t-purple-500 border-r-purple-500/50 rounded-full animate-spin"></div>
                  {/* Inner bot icon */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Bot className="h-4 w-4 text-purple-400" />
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  {/* Primary status — last tool call, persists until next tool call */}
                  <div className="flex items-baseline gap-0.5">
                    <span className="text-sm text-zinc-300 font-medium">
                      {streamingActivity || 'Processing'}
                    </span>
                    {!isThinking && (
                      <span className="flex gap-0.5 items-end pb-0.5 ml-0.5">
                        <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1s' }}></span>
                        <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms', animationDuration: '1s' }}></span>
                        <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms', animationDuration: '1s' }}></span>
                      </span>
                    )}
                  </div>

                  {/* Thinking line — only shown when actively thinking */}
                  {isThinking && (
                    <div className="flex items-baseline gap-0.5">
                      <span className="text-xs text-zinc-500 font-mono">💭 Thinking</span>
                      <span className="flex gap-0.5 items-end pb-0.5 ml-0.5">
                        <span className="inline-block w-0.5 h-0.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1s' }}></span>
                        <span className="inline-block w-0.5 h-0.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '150ms', animationDuration: '1s' }}></span>
                        <span className="inline-block w-0.5 h-0.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '300ms', animationDuration: '1s' }}></span>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black via-black to-transparent">
          <div className="w-full md:max-w-5xl mx-auto">
            {/* Image Preview Strip */}
            {attachedImages.length > 0 && (
              <div className="flex items-center gap-3 mb-3 p-3 border border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md overflow-x-auto shadow-2xl">
                {attachedImages.map((img, idx) => (
                  <div key={idx} className="relative group shrink-0">
                    <img
                      src={img.preview}
                      alt={`Attachment ${idx + 1}`}
                      className="h-[4rem] w-[4rem] object-cover border border-zinc-700/60 rounded-lg shadow-sm"
                    />
                    <button
                      onClick={() => setAttachedImages(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute -top-2 -right-2 h-6 w-6 rounded-full bg-zinc-800/95 border border-zinc-600 flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-zinc-700 hover:scale-105 transition-all shadow-md backdrop-blur-sm"
                    >
                      <X className="h-3.5 w-3.5 text-zinc-300" />
                    </button>
                  </div>
                ))}
                <span className="text-[10.5px] text-zinc-500 font-mono uppercase tracking-widest shrink-0 px-2 pl-3 border-l border-zinc-800/50">
                  {attachedImages.length} / 5
                </span>
              </div>
            )}
            <form
              onSubmit={handleSubmit}
              className="flex items-end gap-1.5 border border-zinc-700/70 bg-zinc-950 shadow-2xl focus-within:border-zinc-500 focus-within:ring-2 focus-within:ring-zinc-800 transition-all p-1.5"
              onDrop={(e) => {
                e.preventDefault();
                const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
                if (files.length === 0) return;
                const remaining = 5 - attachedImages.length;
                files.slice(0, remaining).forEach(file => {
                  const reader = new FileReader();
                  reader.onload = (ev) => {
                    const base64 = ev.target?.result as string;
                    setAttachedImages(prev => prev.length < 5 ? [...prev, { preview: base64, base64 }] : prev);
                  };
                  reader.readAsDataURL(file);
                });
              }}
              onDragOver={(e) => e.preventDefault()}
            >
              <div className="pl-4 pr-2 py-4 text-zinc-500 shrink-0">
                <Terminal className={cn("h-4 w-4", isLoading ? "animate-pulse text-green-500" : "")} />
              </div>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  // Auto-resize
                  const ta = e.target;
                  ta.style.height = 'auto';
                  ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (input.trim() || attachedImages.length > 0) {
                      handleSubmit(e as unknown as React.FormEvent);
                    }
                  }
                }}
                onPaste={(e) => {
                  const items = Array.from(e.clipboardData.items);
                  const imageItems = items.filter(item => item.type.startsWith('image/'));
                  if (imageItems.length === 0) return;
                  e.preventDefault();
                  const remaining = 5 - attachedImages.length;
                  imageItems.slice(0, remaining).forEach(item => {
                    const file = item.getAsFile();
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = (ev) => {
                      const base64 = ev.target?.result as string;
                      setAttachedImages(prev => prev.length < 5 ? [...prev, { preview: base64, base64 }] : prev);
                    };
                    reader.readAsDataURL(file);
                  });
                }}
                placeholder={isLoading ? "Agent is processing..." : "Enter command... (Shift+Enter for new line)"}
                disabled={isLoading}
                className="flex-1 bg-transparent py-3 pr-2 text-[15px] focus:outline-none font-mono text-zinc-100 placeholder:text-zinc-500 resize-none min-h-[44px] max-h-[200px] leading-relaxed"
                rows={1}
                autoFocus
              />
              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  const remaining = 5 - attachedImages.length;
                  files.slice(0, remaining).forEach(file => {
                    const reader = new FileReader();
                    reader.onload = (ev) => {
                      const base64 = ev.target?.result as string;
                      setAttachedImages(prev => prev.length < 5 ? [...prev, { preview: base64, base64 }] : prev);
                    };
                    reader.readAsDataURL(file);
                  });
                  e.target.value = ''; // reset so same file can be re-selected
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || attachedImages.length >= 5}
                className="p-2.5 text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0 self-end mb-1 relative top-[1px]"
                title={attachedImages.length >= 5 ? 'Max 5 images' : 'Attach images'}
              >
                <ImageIcon className="h-[18px] w-[18px]" />
              </button>
              <button
                type="submit"
                disabled={isLoading || (!input.trim() && attachedImages.length === 0)}
                className="px-4 py-2 bg-white text-black font-semibold text-[11px] uppercase tracking-wider border border-transparent hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all self-end mb-1 shrink-0 flex items-center justify-center"
              >
                <span className="hidden md:inline">Execute</span>
                <Send className="h-4 w-4 md:hidden" />
              </button>
            </form>
            <div className="text-center mt-2">
              <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                Synapses that connect agents
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
