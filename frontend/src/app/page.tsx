'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Settings, Terminal, Sun, Moon, Plus } from 'lucide-react';

import { SettingsModal } from '@/components/SettingsModal';
import { AuthPrompt } from '@/components/AuthPrompt';
import { EmailList } from '@/components/EmailList';
import { EmailRenderer } from '@/components/EmailRenderer';
import { DriveList } from '@/components/DriveList';
import { EventList } from '@/components/EventList';
import { LocalFileList } from '@/components/LocalFileList';
import { EmailComposer } from '@/components/EmailComposer';
import { CollectDataForm } from '@/components/CollectDataForm';

import { renderTextContent, cn } from '@/lib/utils';
import { Message, SystemStatus } from '@/types';

export default function Home() {
  const [sessionId, setSessionId] = useState(() => {
    const c: any = (globalThis as any).crypto;
    if (c?.randomUUID) return c.randomUUID();
    return `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  });

  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'System Internal v1.0. Ready for input.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [agentName, setAgentName] = useState('Loading...');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [credentials, setCredentials] = useState(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [streamingActivity, setStreamingActivity] = useState<string | null>(null);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

  // Initial Data Fetch
  useEffect(() => {
    // 1. Get Agent Name
    fetch('/api/settings').then(r => r.json()).then(d => {
      setAgentName(d.agent_name || 'System Agent');
    }).catch(() => setAgentName('Offline'));
    // 2. Get Credentials (masked)
    fetch('/api/config').then(r => r.json()).then(d => setCredentials(d)).catch(console.error);
    // 3. Get Status
    refreshSystemStatus();
  }, []);

  // State to track if a draft has been sent
  const [sentDrafts, setSentDrafts] = useState<Set<number>>(new Set());

  const handleSendEmail = (index: number, to: string, cc: string, bcc: string, subject: string, body: string) => {
    setSentDrafts(prev => new Set(prev).add(index));
    let command = `Confirmed. Please immediately execute the send_email tool. To: "${to}", Subject: "${subject}", Body: "${body}"`;
    if (cc) command += `, Cc: "${cc}"`;
    if (bcc) command += `, Bcc: "${bcc}"`;

    // Send directly
    processMessage(command);
  };

  const handleNewChat = () => {
    const c: any = (globalThis as any).crypto;
    const newSessionId = c?.randomUUID?.() ?? `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    setSessionId(newSessionId);
    setMessages([{ role: 'assistant', content: 'System Internal v1.0. Ready for input.' }]);
    setStreamingActivity(null);
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

  const handleUpdateSettings = async (name: string, model: string, mode: string, keys: any) => {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_name: name,
        model: model,
        mode: mode,
        openai_key: keys.openai_key,
        anthropic_key: keys.anthropic_key,
        gemini_key: keys.gemini_key,
        bedrock_api_key: keys.bedrock_api_key,
        bedrock_inference_profile: keys.bedrock_inference_profile,
        aws_access_key_id: keys.aws_access_key_id,
        aws_secret_access_key: keys.aws_secret_access_key,
        aws_session_token: keys.aws_session_token,
        aws_region: keys.aws_region,
        sql_connection_string: keys.sql_connection_string,
        n8n_url: keys.n8n_url,
        n8n_api_key: keys.n8n_api_key,
        google_maps_api_key: keys.google_maps_api_key,
        global_config: keys.global_config,
        vault_enabled: keys.vault_enabled,
        vault_threshold: keys.vault_threshold,
      })
    });
    setAgentName(name);
    // Refresh status to update header
    fetch('/api/status').then(r => r.json()).then(d => setSystemStatus(d));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    await processMessage(userMessage);
  };

  const handleEmailClick = async (emailId: string) => {
    const userMessage = `Read email ${emailId}`;
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    await processMessage(userMessage);
  };

  const handleSummarizeFile = async (path: string) => {
    const userMessage = `Summarize the content of ${path}`;
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    await processMessage(userMessage);
  };

  const handleLocateFile = async (path: string) => {
    const userMessage = `Locate file ${path}`;
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    await processMessage(userMessage);
  };

  const handleOpenFile = async (path: string) => {
    setMessages(prev => [...prev, { role: 'user', content: `Open file: ${path}` }]);
    await processMessage(`Open file: ${path}`);
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
  const processMessage = async (content: string) => {
    setIsLoading(true);
    setStreamingActivity(null);

    // Try SSE streaming first
    try {
      await processMessageSSE(content);
    } catch (sseError) {
      console.error('[SSE] SSE failed, falling back to HTTP:', sseError);
      // Fallback to HTTP
      await processMessageHTTP(content);
    } finally {
      setIsLoading(false);
      setStreamingActivity(null);
    }
  };

  // SSE Streaming implementation
  const processMessageSSE = async (content: string) => {
    return new Promise<void>((resolve, reject) => {
      const params = new URLSearchParams({
        message: content,
        session_id: sessionId,
      });

      // Use POST for SSE to send body data
      console.log('[SSE] Attempting SSE connection to /api/chat/stream');
      fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: sessionId, agent_id: currentAgentId }),
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
                    case 'status':
                      setStreamingActivity(data.message);
                      break;
                    case 'thinking':
                      setStreamingActivity('🤔 Thinking');
                      break;
                    case 'tool_execution':
                      const toolDisplayName = data.tool_name
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (l: string) => l.toUpperCase());
                      setStreamingActivity(`🔧 ${toolDisplayName}`);
                      break;
                    case 'tool_result':
                      setStreamingActivity(`✓ Processing results`);
                      break;
                    case 'response':
                      // Final response
                      setMessages(prev => [...prev, {
                        role: 'assistant',
                        content: data.content,
                        intent: data.intent,
                        data: data.data,
                        tool: data.tool_name
                      }]);
                      break;
                    // Orchestration events (when chatting with orchestrator agents)
                    case 'orchestration_start':
                      setStreamingActivity(`Orchestration started`);
                      break;
                    case 'step_start':
                      setStreamingActivity(`▶ ${data.step_name || 'Step'}`);
                      break;
                    case 'step_complete':
                      setStreamingActivity(`✓ ${data.step_name || 'Step'} complete`);
                      break;
                    case 'step_error':
                      setStreamingActivity(`✗ Step failed`);
                      break;
                    case 'orchestration_complete':
                      setStreamingActivity(`Orchestration ${data.status}`);
                      break;
                    case 'orchestration_error':
                      setStreamingActivity(`Orchestration error`);
                      break;
                    case 'human_input_required':
                      setStreamingActivity(`Waiting for human input`);
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
  const processMessageHTTP = async (content: string) => {
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: sessionId }),
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

  return (
    <main className={cn("flex h-screen bg-black text-white font-mono overflow-hidden", theme === 'light' ? 'light-mode' : '')}>
      {/* Settings Modal */}
      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => {
          setIsSettingsOpen(false);
          refreshSystemStatus();
        }}
        onSave={handleUpdateSettings}
        credentials={credentials}
      />

      <div className="flex-1 flex flex-col w-full border-x border-zinc-800 shadow-2xl relative">
        {/* Header */}
        <header className="h-14 border-b border-zinc-800 bg-zinc-950 px-6 shrink-0 z-10">
          <div className='w-full md:max-w-5xl mx-auto h-full flex items-center justify-between'>
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_#22c55e]"></div>
              <h1 className="text-base font-bold tracking-widest uppercase text-zinc-100">
                {agentName} <span className="text-zinc-500">-</span> <span className="text-zinc-400">Ask Anything</span>
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
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400">Model:</span>
                  <span className="text-zinc-200">{systemStatus?.model || 'Loading...'}</span>
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
                            <span className="truncate max-w-[120px]">{name}</span>
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
                onClick={() => setTheme(prev => prev === 'dark' ? 'light' : 'dark')}
                className="p-2 ml-2 hover:bg-zinc-900 rounded text-zinc-400 hover:text-white transition-colors"
                title={theme === 'dark' ? "Switch to Light Mode" : "Switch to Dark Mode"}
              >
                {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>

              <button
                onClick={() => setIsSettingsOpen(true)}
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
            {messages.map((msg, idx) => (
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
                  </div>

                  {/* Dynamic UI based on Intent - Rendered Outside Bubble */}
                  {msg.role === 'assistant' && (
                    <div className="w-full mt-2 pl-1">
                      {msg.intent === 'list_emails' && <EmailList emails={msg.data?.emails || msg.data} onEmailClick={handleEmailClick} />}
                      {msg.intent === 'read_email' && <EmailRenderer email={msg.data} />}
                      {msg.intent === 'list_files' && <DriveList files={msg.data?.files || msg.data} />}
                      {msg.intent === 'list_events' && <EventList events={msg.data?.events || msg.data} />}
                      {msg.intent === 'request_auth' && <AuthPrompt onOpenSettings={() => setIsSettingsOpen(true)} credentials={credentials} />}
                      {msg.intent === 'list_local_files' && <LocalFileList files={msg.data?.files || msg.data} onSummarizeFile={handleSummarizeFile} onLocateFile={handleLocateFile} onOpenFile={handleOpenFile} />}
                      {msg.intent === 'render_local_file' && (
                        <div className="mt-4 p-4 bg-zinc-950 border border-zinc-800 font-mono text-xs whitespace-pre-wrap max-h-96 overflow-auto text-zinc-300">
                          {msg.data.content}
                        </div>
                      )}
                      {msg.intent === 'draft_email' && !sentDrafts.has(idx) && (
                        <EmailComposer
                          to={msg.data.to}
                          initialSubject={msg.data.subject}
                          initialBody={msg.data.body}
                          onSend={(t, c, b, s, bo) => handleSendEmail(idx, t, c, b, s, bo)}
                          onCancel={() => setSentDrafts(prev => new Set(prev).add(idx))}
                        />
                      )}
                      {msg.intent === 'draft_email' && sentDrafts.has(idx) && (
                        <div className="mt-2 text-xs text-zinc-500 italic border-l-2 border-zinc-800 pl-2">
                          Draft processed.
                        </div>
                      )}
                      {msg.intent === 'collect_data' && msg.data && (
                        <CollectDataForm data={msg.data} onSubmit={handleCollectDataSubmit} />
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading Indicator */}
            {isLoading && (
              <div className="flex gap-4 max-w-3xl items-center">
                {/* Spinning Bot Icon with Ring */}
                <div className="relative h-8 w-8 shrink-0">
                  {/* Outer spinning ring */}
                  <div className="absolute inset-0 border-2 border-transparent border-t-purple-500 border-r-purple-500/50 rounded-full animate-spin"></div>
                  {/* Inner bot icon */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Bot className="h-4 w-4 text-purple-400" />
                  </div>
                </div>

                {/* Status text with animated dots */}
                <div className="flex items-baseline gap-0.5">
                  <span className="text-sm text-zinc-300 font-medium">
                    {streamingActivity || 'Processing'}
                  </span>
                  {/* Animated dots - smaller and inline */}
                  <span className="flex gap-0.5 items-end pb-0.5">
                    <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1s' }}></span>
                    <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms', animationDuration: '1s' }}></span>
                    <span className="inline-block w-0.5 h-0.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms', animationDuration: '1s' }}></span>
                  </span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black via-black to-transparent">
          <div className="w-full md:max-w-5xl mx-auto">
            <form
              onSubmit={handleSubmit}
              className="flex items-center gap-0 border border-zinc-700 bg-black shadow-2xl focus-within:border-white focus-within:ring-1 focus-within:ring-white transition-all overflow-hidden"
            >
              <div className="pl-4 pr-2 text-zinc-500">
                <Terminal className={cn("h-4 w-4", isLoading ? "animate-pulse text-green-500" : "")} />
              </div>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={isLoading ? "Agent is processing..." : "Enter command..."}
                disabled={isLoading}
                className="flex-1 bg-transparent p-4 text-sm focus:outline-none font-mono text-white placeholder:text-zinc-500"
                autoFocus
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="p-4 md:px-6 bg-zinc-900 border-l border-zinc-700 text-zinc-300 font-bold text-xs uppercase font-mono hover:bg-zinc-800 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-all"
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
