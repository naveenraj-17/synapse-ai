/* eslint-disable @typescript-eslint/no-explicit-any */
import { Bot, Plus, Save, Trash, ChevronDown, ChevronRight, Lock, Sparkles, Eye, EyeOff, Loader2 } from 'lucide-react';
import { CAPABILITIES, AUTO_TOOLS_BY_TYPE } from './types';
import { renderTextContent } from '@/lib/utils';

interface AgentsTabProps {
    agents: any[];
    selectedAgentId: string | null;
    setSelectedAgentId: (id: string | null) => void;
    draftAgent: any;
    setDraftAgent: (agent: any) => void;
    availableCapabilities: any[];
    customTools: any[];
    onSaveAgent: () => void;
    onDeleteAgent: (id: string) => void;
    providers?: Record<string, { available: boolean; models: string[] }>;
    defaultModel?: string;
}

import React, { useState, useEffect } from 'react';

export const AgentsTab = ({
    agents, selectedAgentId, setSelectedAgentId,
    draftAgent, setDraftAgent, availableCapabilities, customTools,
    onSaveAgent, onDeleteAgent, providers, defaultModel
}: AgentsTabProps) => {
    const [repos, setRepos] = useState<any[]>([]);
    const [dbConfigs, setDbConfigs] = useState<any[]>([]);
    const [agentTypes, setAgentTypes] = useState<{value: string; label: string; description: string}[]>([]);
    const [expandedCaps, setExpandedCaps] = useState<Set<string>>(new Set());
    const [promptDescription, setPromptDescription] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [showPreview, setShowPreview] = useState(false);

    useEffect(() => {
        fetch('/api/repos')
            .then(res => res.json())
            .then(data => setRepos(data))
            .catch(err => console.error("Failed to fetch repos", err));
        fetch('/api/db-configs')
            .then(res => res.json())
            .then(data => setDbConfigs(data))
            .catch(err => console.error("Failed to fetch DB configs", err));
        fetch('/api/agent-types')
            .then(res => res.json())
            .then(data => setAgentTypes(data.types || []))
            .catch(err => console.error("Failed to fetch agent types", err));
    }, []);

    const toggleExpand = (capId: string) => {
        setExpandedCaps(prev => {
            const next = new Set(prev);
            if (next.has(capId)) next.delete(capId);
            else next.add(capId);
            return next;
        });
    };

    const toggleGroupTools = (cap: any) => {
        const allGroupEnabled = cap.tools.every((t: string) => draftAgent.tools.includes(t));
        if (draftAgent.tools.includes("all")) {
            // Switch from "all" to explicit list minus this group
            const allToolsFlat = availableCapabilities.flatMap((c: any) => c.tools);
            if (allGroupEnabled) {
                const newTools = allToolsFlat.filter((t: string) => !cap.tools.includes(t));
                setDraftAgent({ ...draftAgent, tools: newTools });
            } else {
                setDraftAgent({ ...draftAgent, tools: [...draftAgent.tools, ...cap.tools] });
            }
        } else {
            if (allGroupEnabled) {
                const newTools = draftAgent.tools.filter((t: string) => !cap.tools.includes(t));
                setDraftAgent({ ...draftAgent, tools: newTools });
            } else {
                const newTools = [...draftAgent.tools, ...cap.tools.filter((t: string) => !draftAgent.tools.includes(t))];
                setDraftAgent({ ...draftAgent, tools: newTools });
            }
        }
    };

    const toggleSingleTool = (toolName: string, cap: any) => {
        if (draftAgent.tools.includes("all")) {
            // Switch from "all" to explicit list minus this tool
            const allToolsFlat = availableCapabilities.flatMap((c: any) => c.tools);
            const newTools = allToolsFlat.filter((t: string) => t !== toolName);
            setDraftAgent({ ...draftAgent, tools: newTools });
        } else {
            if (draftAgent.tools.includes(toolName)) {
                const newTools = draftAgent.tools.filter((t: string) => t !== toolName);
                setDraftAgent({ ...draftAgent, tools: newTools });
            } else {
                setDraftAgent({ ...draftAgent, tools: [...draftAgent.tools, toolName] });
            }
        }
    };

    const generatePrompt = async () => {
        if (!promptDescription.trim()) return;
        setIsGenerating(true);
        try {
            // Collect selected tool names with descriptions
            const agentType = draftAgent.type || 'conversational';
            const autoToolNames = [
                ...(AUTO_TOOLS_BY_TYPE.all_types || []),
                ...(AUTO_TOOLS_BY_TYPE[agentType] || []),
            ];
            const selectedTools: string[] = [];
            for (const cap of availableCapabilities) {
                for (const tool of (cap.toolDetails || cap.tools.map((t: string) => ({ name: t, description: '' })))) {
                    if (
                        autoToolNames.includes(tool.name) ||
                        draftAgent.tools.includes('all') ||
                        draftAgent.tools.includes(tool.name)
                    ) {
                        selectedTools.push(tool.description ? `${tool.name} - ${tool.description}` : tool.name);
                    }
                }
            }

            const res = await fetch('/api/agents/generate-prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: promptDescription,
                    agent_type: agentType,
                    tools: selectedTools,
                    existing_prompt: draftAgent.system_prompt || '',
                }),
                signal: AbortSignal.timeout(180_000), // 3 minutes timeout for LLM generation
            });
            if (!res.ok) throw new Error('Failed to generate prompt');
            const data = await res.json();
            setDraftAgent({ ...draftAgent, system_prompt: data.system_prompt });
            setPromptDescription('');
        } catch (err) {
            console.error('Failed to generate prompt:', err);
        } finally {
            setIsGenerating(false);
        }
    };

    return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-10">
        {/* List */}
        <div className="md:col-span-4 border-r border-zinc-800 pr-4 flex flex-col sticky top-0 h-fit self-start">
            <div className="mb-4 flex justify-between items-center">
                <h3 className="text-sm font-bold text-zinc-400">YOUR AGENTS</h3>
                <button
                    onClick={() => {
                        const newAgent = {
                            id: `agent_${Date.now()}`,
                            name: "New Agent",
                            description: "A custom agent.",
                            system_prompt: "You are a helpful assistant.",
                            tools: [],
                            repos: [],
                            type: "conversational",
                            avatar: "default"
                        };
                        setDraftAgent(newAgent);
                        setSelectedAgentId(newAgent.id);
                    }}
                    className="p-1.5 hover:bg-zinc-800 text-white transition-colors border border-dashed border-zinc-600 hover:border-white"
                    title="Create New Agent"
                >
                    <Plus className="h-4 w-4" />
                </button>
            </div>

            <div className="space-y-2 flex-1">
                {Array.isArray(agents) && agents.map((a: any) => (
                    <div
                        key={a.id}
                        onClick={() => {
                            setSelectedAgentId(a.id);
                            setDraftAgent({ ...a }); // Deep copy to draft
                        }}
                        className={`p-3 border cursor-pointer transition-all group relative
                            ${selectedAgentId === a.id
                                ? 'bg-zinc-900 border-white shadow-lg'
                                : 'bg-black border-zinc-800 hover:border-zinc-600'
                            }`}
                    >
                        <div className="flex items-center gap-3">
                            <div className={`h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold
                                ${selectedAgentId === a.id ? 'bg-white text-black' : 'bg-zinc-800 text-zinc-400'}
                            `}>
                                {a.name.substring(0, 2).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-xs font-bold text-white truncate">{a.name}</div>
                                <div className="text-[10px] text-zinc-500 truncate">{a.description}</div>
                            </div>
                        </div>
                        {a.id !== 'synapse' && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onDeleteAgent(a.id);
                                }}
                                className="absolute top-2 right-2 p-1 text-zinc-600 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                                <Trash className="h-3 w-3" />
                            </button>
                        )}
                    </div>
                ))}
            </div>
        </div>

        {/* Edit Form */}
        <div className="md:col-span-8 pl-4">
            {draftAgent ? (
                <div className="space-y-6 h-full flex flex-col pb-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold text-white flex items-center gap-2">
                            <div className={`h-2 w-2 rounded-full ${draftAgent.id === 'synapse' ? 'bg-blue-500' : 'bg-purple-500'}`} />
                            EDITING: {draftAgent.name.toUpperCase()}
                        </h3>
                        <button
                            onClick={onSaveAgent}
                            className="flex items-center gap-2 px-4 py-1.5 bg-white text-black text-xs font-bold hover:bg-zinc-200"
                        >
                            <Save className="h-3 w-3" /> SAVE AGENT
                        </button>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Name</label>
                            <input
                                type="text"
                                value={draftAgent.name}
                                onChange={e => setDraftAgent({ ...draftAgent, name: e.target.value })}
                                className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Description</label>
                            <input
                                type="text"
                                value={draftAgent.description}
                                onChange={e => setDraftAgent({ ...draftAgent, description: e.target.value })}
                                className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Agent Type</label>
                            <select
                                value={draftAgent.type || 'conversational'}
                                onChange={e => {
                                    const newType = e.target.value;
                                    // Remove old type-specific auto-tools from explicit list
                                    const oldAutoTools = AUTO_TOOLS_BY_TYPE[draftAgent.type] || [];
                                    const cleanedTools = draftAgent.tools.filter(
                                        (t: string) => !oldAutoTools.includes(t)
                                    );
                                    setDraftAgent({ ...draftAgent, type: newType, tools: cleanedTools });
                                }}
                                className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                            >
                                {agentTypes.map(t => (
                                    <option key={t.value} value={t.value}>{t.label}</option>
                                ))}
                            </select>
                            <p className="text-[9px] text-zinc-500 mt-1">
                                {agentTypes.find(t => t.value === (draftAgent.type || 'conversational'))?.description}
                            </p>
                        </div>

                        {/* Model Selection */}
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Model</label>
                            <select
                                value={draftAgent.model || ''}
                                onChange={e => setDraftAgent({ ...draftAgent, model: e.target.value || null })}
                                className="w-full bg-zinc-950 border border-zinc-800 p-3 text-xs text-white focus:border-white focus:outline-none"
                            >
                                <option value="">Use Default ({defaultModel || 'not set'})</option>
                                {providers && Object.entries(providers).map(([providerKey, info]) => {
                                    if (!info.available || info.models.length === 0) return null;
                                    const providerLabel = providerKey.charAt(0).toUpperCase() + providerKey.slice(1);
                                    return (
                                        <optgroup key={providerKey} label={providerLabel}>
                                            {info.models.map((m: string) => (
                                                <option key={m} value={m}>{m}</option>
                                            ))}
                                        </optgroup>
                                    );
                                })}
                            </select>
                            <p className="text-[9px] text-zinc-500 mt-1">Override the default model for this agent. Leave empty to use the system default.</p>
                        </div>
                    </div>

                    {draftAgent.type === 'code' && (
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Linked Repositories</label>
                            <div className="bg-zinc-950 border border-zinc-800 p-3 flex flex-wrap gap-2 min-h-[50px]">
                                {repos.length === 0 && <span className="text-xs text-zinc-500">No repositories indexed yet.</span>}
                                {repos.map(repo => {
                                    const isLinked = draftAgent.repos?.includes(repo.id);
                                    return (
                                        <button
                                            key={repo.id}
                                            onClick={() => {
                                                const currentRepos = draftAgent.repos || [];
                                                if (isLinked) {
                                                    setDraftAgent({ ...draftAgent, repos: currentRepos.filter((id: string) => id !== repo.id) });
                                                } else {
                                                    setDraftAgent({ ...draftAgent, repos: [...currentRepos, repo.id] });
                                                }
                                            }}
                                            className={`px-3 py-1.5 text-xs font-bold border transition-colors ${
                                                isLinked
                                                    ? 'bg-white text-black border-white'
                                                    : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-500'
                                            }`}
                                        >
                                            {repo.name} {isLinked && '✓'}
                                        </button>
                                    );
                                })}
                            </div>
                            <p className="text-[9px] text-zinc-500 mt-1">Select indexed repositories for semantic code search access.</p>
                        </div>
                    )}

                    {draftAgent.type === 'code' && (
                        <div className="space-y-1">
                            <label className="text-[10px] font-bold text-zinc-500 uppercase">Linked Databases</label>
                            <div className="bg-zinc-950 border border-zinc-800 p-3 flex flex-wrap gap-2 min-h-[50px]">
                                {dbConfigs.length === 0 && <span className="text-xs text-zinc-500">No databases configured yet.</span>}
                                {dbConfigs.map((db: any) => {
                                    const isLinked = draftAgent.db_configs?.includes(db.id);
                                    return (
                                        <button
                                            key={db.id}
                                            onClick={() => {
                                                const currentDbs = draftAgent.db_configs || [];
                                                if (isLinked) {
                                                    setDraftAgent({ ...draftAgent, db_configs: currentDbs.filter((id: string) => id !== db.id) });
                                                } else {
                                                    setDraftAgent({ ...draftAgent, db_configs: [...currentDbs, db.id] });
                                                }
                                            }}
                                            className={`px-3 py-1.5 text-xs font-bold border transition-colors ${
                                                isLinked
                                                    ? 'bg-white text-black border-white'
                                                    : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-500'
                                            }`}
                                        >
                                            {db.name} <span className="opacity-50">{db.db_type}</span> {isLinked && '✓'}
                                        </button>
                                    );
                                })}
                            </div>
                            <p className="text-[9px] text-zinc-500 mt-1">Select databases to inject schema context into the agent's system prompt.</p>
                        </div>
                    )}

                    {draftAgent.id === 'synapse' ? (
                        <div className="p-4 bg-blue-900/10 border border-blue-900/30 text-blue-300 text-xs text-center">
                            <div className="font-bold mb-1">System Managed</div>
                            The capabilities and brain of the default agent are managed by the core system for optimal business performance.
                        </div>
                    ) : (
                        <>
                            <div className="space-y-3">
                                <label className="text-[10px] font-bold text-zinc-500 uppercase">Capabilities (Tools)</label>
                                {(() => {
                                    const agentType = draftAgent.type || 'conversational';
                                    const autoTools = new Set([
                                        ...(AUTO_TOOLS_BY_TYPE.all_types || []),
                                        ...(AUTO_TOOLS_BY_TYPE[agentType] || []),
                                    ]);
                                    return (
                                <div className="grid grid-cols-2 gap-4">
                                    {availableCapabilities.map((cap: any) => {
                                        const toolDetails: {name: string, description: string}[] = cap.toolDetails || cap.tools.map((t: string) => ({ name: t, description: '' }));
                                        const hasMultipleTools = toolDetails.length > 1;
                                        const isExpanded = expandedCaps.has(cap.id);

                                        // Check if all tools in this group are auto-included for this agent type
                                        const isAutoGroup = cap.tools.every((t: string) => autoTools.has(t));

                                        const enabledCount = cap.tools.filter((t: string) =>
                                            isAutoGroup || draftAgent.tools.includes("all") || draftAgent.tools.includes(t)
                                        ).length;
                                        const allGroupEnabled = enabledCount === cap.tools.length;
                                        const someEnabled = enabledCount > 0 && !allGroupEnabled;

                                        return (
                                            <div
                                                key={cap.id}
                                                className={`border transition-colors
                                                    ${isAutoGroup
                                                        ? 'bg-zinc-900/60 border-blue-900/40'
                                                        : allGroupEnabled
                                                            ? 'bg-zinc-900 border-zinc-600'
                                                            : someEnabled
                                                                ? 'bg-zinc-900/50 border-zinc-700'
                                                                : 'bg-black border-zinc-800 opacity-50'
                                                    }`}
                                            >
                                                {/* Group header */}
                                                <div className={`p-4 flex items-center gap-2 transition-colors ${isAutoGroup ? 'cursor-default' : 'cursor-pointer hover:bg-zinc-800/30'}`}
                                                    onClick={() => {
                                                        if (isAutoGroup) return;
                                                        if (hasMultipleTools) {
                                                            toggleExpand(cap.id);
                                                        } else {
                                                            toggleGroupTools(cap);
                                                        }
                                                    }}
                                                >
                                                    {/* Group checkbox or lock icon */}
                                                    {isAutoGroup ? (
                                                        <Lock className="w-3 h-3 text-blue-400 flex-shrink-0" />
                                                    ) : (
                                                    <div
                                                        onClick={(e) => {
                                                            if (hasMultipleTools) {
                                                                e.stopPropagation();
                                                                toggleGroupTools(cap);
                                                            }
                                                        }}
                                                        className={`w-3 h-3 border flex-shrink-0 flex items-center justify-center
                                                            ${allGroupEnabled
                                                                ? 'bg-green-500 border-green-500'
                                                                : someEnabled
                                                                    ? 'bg-yellow-500 border-yellow-500'
                                                                    : 'border-zinc-600'
                                                            }`}
                                                    >
                                                        {someEnabled && <div className="w-1.5 h-0.5 bg-white"></div>}
                                                    </div>
                                                    )}
                                                    <span className="text-xs font-bold text-white truncate flex-1">{cap.label}</span>
                                                    {isAutoGroup && <span className="text-[9px] px-1.5 py-0.5 bg-blue-900/50 text-blue-400 border border-blue-900 rounded">DEFAULT</span>}
                                                    {!isAutoGroup && cap.toolType === 'custom' && <span className="text-[9px] px-1 bg-zinc-800 text-zinc-400 rounded">CUSTOM</span>}
                                                    {!isAutoGroup && cap.toolType === 'mcp' && <span className="text-[9px] px-1 bg-blue-900/50 text-blue-400 border border-blue-900 rounded">MCP</span>}
                                                    {!isAutoGroup && hasMultipleTools && (
                                                        <span className="text-[9px] text-zinc-500">{enabledCount}/{cap.tools.length}</span>
                                                    )}
                                                    {!isAutoGroup && hasMultipleTools && (
                                                        isExpanded
                                                            ? <ChevronDown className="h-3 w-3 text-zinc-500 flex-shrink-0" />
                                                            : <ChevronRight className="h-3 w-3 text-zinc-500 flex-shrink-0" />
                                                    )}
                                                </div>

                                                {/* Group description */}
                                                {!isExpanded && (
                                                    <div className="px-4 pb-3 -mt-1">
                                                        <p className="text-[9px] text-zinc-500 pl-5 truncate">
                                                            {isAutoGroup ? `Included by default for ${agentType} agents` : cap.description}
                                                        </p>
                                                    </div>
                                                )}

                                                {/* Expanded: individual tools (not for auto groups) */}
                                                {isExpanded && hasMultipleTools && !isAutoGroup && (
                                                    <div className="border-t border-zinc-800 px-3 py-2 space-y-1 max-h-[200px] overflow-y-auto">
                                                        {toolDetails.map((tool: {name: string, description: string}) => {
                                                            const isToolAuto = autoTools.has(tool.name);
                                                            const isToolEnabled = isToolAuto || draftAgent.tools.includes("all") || draftAgent.tools.includes(tool.name);
                                                            return (
                                                                <div
                                                                    key={tool.name}
                                                                    onClick={() => !isToolAuto && toggleSingleTool(tool.name, cap)}
                                                                    className={`flex gap-2.5 py-1.5 px-2 rounded transition-colors ${isToolAuto ? 'cursor-default opacity-60' : 'cursor-pointer hover:bg-zinc-800/40'}`}
                                                                >
                                                                    {isToolAuto ? (
                                                                        <Lock className="w-2.5 h-2.5 text-blue-400 flex-shrink-0 mt-[3px]" />
                                                                    ) : (
                                                                    <div className={`w-2.5 h-2.5 border flex-shrink-0 mt-[3px]
                                                                        ${isToolEnabled
                                                                            ? 'bg-green-500 border-green-500'
                                                                            : 'border-zinc-600'
                                                                        }`}
                                                                    ></div>
                                                                    )}
                                                                    <div className="min-w-0 flex-1">
                                                                        <div className="text-[10px] font-mono text-zinc-300">{tool.name}</div>
                                                                        {tool.description && (
                                                                            <p className="text-[9px] text-zinc-600 mt-0.5 leading-tight">{tool.description}</p>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                                    );
                                })()}
                            </div>

                            {/* Prompt Generator */}
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold text-zinc-500 uppercase flex items-center gap-1.5">
                                    <Sparkles className="h-3 w-3" /> AI Prompt Writer
                                </label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={promptDescription}
                                        onChange={e => setPromptDescription(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && !isGenerating && generatePrompt()}
                                        placeholder="Describe what this agent should do... e.g. 'A customer support agent for a SaaS product'"
                                        className="flex-1 bg-zinc-950 border border-zinc-800 px-3 py-2 text-xs text-white focus:border-purple-500 focus:outline-none placeholder:text-zinc-600"
                                    />
                                    <button
                                        onClick={generatePrompt}
                                        disabled={isGenerating || !promptDescription.trim()}
                                        className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white text-xs font-bold flex items-center gap-2 transition-colors"
                                    >
                                        {isGenerating ? (
                                            <><Loader2 className="h-3 w-3 animate-spin" /> GENERATING...</>
                                        ) : (
                                            <><Sparkles className="h-3 w-3" /> GENERATE</>
                                        )}
                                    </button>
                                </div>
                                <p className="text-[9px] text-zinc-600">Describe the agent&apos;s purpose and the AI will generate a comprehensive system prompt. Tools and date/time context are auto-injected at runtime.</p>
                            </div>

                            {/* System Prompt with Preview */}
                            <div className="space-y-1 flex-1 flex flex-col min-h-0">
                                <div className="flex items-center justify-between">
                                    <label className="text-[10px] font-bold text-zinc-500 uppercase">System Prompt (The Brain)</label>
                                    <button
                                        onClick={() => setShowPreview(!showPreview)}
                                        className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-500 hover:text-white transition-colors px-2 py-1"
                                    >
                                        {showPreview ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                        {showPreview ? 'EDIT' : 'PREVIEW'}
                                    </button>
                                </div>
                                {showPreview ? (
                                    <div className="w-full flex-1 min-h-[200px] max-h-[500px] overflow-y-auto bg-zinc-950 border border-zinc-800 p-4 text-sm text-zinc-300 leading-relaxed">
                                        {renderTextContent(draftAgent.system_prompt || '*No system prompt yet.*')}
                                    </div>
                                ) : (
                                    <textarea
                                        value={draftAgent.system_prompt}
                                        onChange={e => setDraftAgent({ ...draftAgent, system_prompt: e.target.value })}
                                        className="w-full flex-1 min-h-[200px] bg-zinc-950 border border-zinc-800 p-3 text-xs font-mono text-zinc-300 focus:border-white focus:outline-none resize-none leading-relaxed"
                                    />
                                )}
                            </div>
                        </>
                    )}
                </div>
            ) : (
                <div className="h-full flex flex-col items-center justify-center text-zinc-600 space-y-4">
                    <Bot className="h-12 w-12 opacity-20" />
                    <p className="text-sm">Select an agent to edit or create a new one.</p>
                </div>
            )}
        </div>
    </div>
    );
};
