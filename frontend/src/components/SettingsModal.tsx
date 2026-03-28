/* eslint-disable @typescript-eslint/ban-ts-comment */
/* eslint-disable react/no-unescaped-entities */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useRef } from 'react';
import { Settings, X, Shield, Trash, Cpu, Cloud, Database, LayoutGrid, Bot, Wrench, Server, FolderGit2, Workflow, ScrollText } from 'lucide-react';

import { CAPABILITIES } from './settings/types';
import type { SettingsModalProps, Tab } from './settings/types';
import { GeneralTab } from './settings/GeneralTab';
import { PersonalDetailsTab } from './settings/PersonalDetailsTab';
import { MemoryTab } from './settings/MemoryTab';
import { AgentsTab } from './settings/AgentsTab';
import { CustomToolsTab } from './settings/CustomToolsTab';
import { DataLabTab } from './settings/DataLabTab';
import { ModelsTab } from './settings/ModelsTab';
import { IntegrationsTab } from './settings/IntegrationsTab';
import { McpServersTab } from './settings/McpServersTab';
import { ConfirmationModal } from './settings/ConfirmationModal';
import { ToastNotification } from './settings/ToastNotification';
import { N8nFullscreenOverlay } from './settings/N8nFullscreenOverlay';
import { ReposTab } from './settings/ReposTab';
import { DBsTab } from './settings/DBsTab';
import { OrchestrationTab } from './settings/OrchestrationTab';
import { LogsTab } from './settings/LogsTab';


export const SettingsModal = ({ isOpen, onClose, onSave, credentials }: SettingsModalProps) => {
    const [activeTab, setActiveTab] = useState<Tab>('general');
    const [agentName, setAgentName] = useState('');
    const [selectedModel, setSelectedModel] = useState('');
    const [mode, setMode] = useState('local'); // local | cloud
    const [localModels, setLocalModels] = useState<string[]>([]);
    const [cloudModels, setCloudModels] = useState<string[]>([]);
    const [providers, setProviders] = useState<Record<string, { available: boolean; models: string[] }>>({});
    const [loadingModels, setLoadingModels] = useState(false);

    // Vault settings
    const [vaultEnabled, setVaultEnabled] = useState(true);
    const [vaultThreshold, setVaultThreshold] = useState(15000);
    const [allowDbWrite, setAllowDbWrite] = useState(false);

    // Keys
    const [openaiKey, setOpenaiKey] = useState('');
    const [anthropicKey, setAnthropicKey] = useState('');
    const [geminiKey, setGeminiKey] = useState('');
    const [bedrockApiKey, setBedrockApiKey] = useState('');
    const [awsRegion, setAwsRegion] = useState('us-east-1');
    const [bedrockInferenceProfile, setBedrockInferenceProfile] = useState('');
    const [bedrockInferenceProfiles, setBedrockInferenceProfiles] = useState<Array<{ id: string; arn: string; name: string; status?: string }>>([]);
    const [loadingInferenceProfiles, setLoadingInferenceProfiles] = useState(false);
    const [sqlConnectionString, setSqlConnectionString] = useState('');

    // Integrations: Google Maps
    const [googleMapsApiKey, setGoogleMapsApiKey] = useState('');

    // Personal Details
    const [pdFirstName, setPdFirstName] = useState('');
    const [pdLastName, setPdLastName] = useState('');
    const [pdEmail, setPdEmail] = useState('');
    const [pdPhone, setPdPhone] = useState('');
    const [pdAddress1, setPdAddress1] = useState('');
    const [pdAddress2, setPdAddress2] = useState('');
    const [pdCity, setPdCity] = useState('');
    const [pdState, setPdState] = useState('');
    const [pdZipcode, setPdZipcode] = useState('');

    // Integrations: n8n
    const [n8nUrl, setN8nUrl] = useState('http://localhost:5678');
    const [n8nApiKey, setN8nApiKey] = useState('');
    const [globalConfig, setGlobalConfig] = useState<{ id: string, key: string, value: string }[]>([]);

    // Agents State
    const [agents, setAgents] = useState<any[]>([]);
    const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
    const [draftAgent, setDraftAgent] = useState<any>(null);


    // Custom Tools State
    const [customTools, setCustomTools] = useState<any[]>([]);
    const [draftTool, setDraftTool] = useState<any>(null);
    const [toolBuilderMode, setToolBuilderMode] = useState<'config' | 'n8n'>('config');
    const [headerRows, setHeaderRows] = useState<{ id: string, key: string, value: string }[]>([]);
    const [showToast, setShowToast] = useState(false);

    // n8n workflows (for Tool Builder dropdown)
    const [n8nWorkflows, setN8nWorkflows] = useState<any[]>([]);
    const [n8nWorkflowsLoading, setN8nWorkflowsLoading] = useState(false);

    // MCP Servers State
    const [mcpServers, setMcpServers] = useState<any[]>([]);
    const [loadingMcp, setLoadingMcp] = useState(false);
    const [draftMcpServer, setDraftMcpServer] = useState<{name: string, command: string, args: string, env: {key:string, value:string}[]}>({
        name: '', command: '', args: '', env: []
    });

    const [availableCapabilities, setAvailableCapabilities] = useState<any[]>(CAPABILITIES);

    const refreshBedrockModels = async () => {
        setLoadingModels(true);
        try {
            const res = await fetch('/api/bedrock/models');
            const data = await res.json();
            const bedrock = Array.isArray(data.models) ? data.models : [];
            if (bedrock.length > 0) {
                setCloudModels(prev => {
                    const nonBedrock = (prev || []).filter((m: string) => !m.startsWith('bedrock.'));
                    return [...nonBedrock, ...bedrock];
                });
            }
        } catch {
            // ignore
        } finally {
            setLoadingModels(false);
        }
    };

    const refreshBedrockInferenceProfiles = async () => {
        setLoadingInferenceProfiles(true);
        try {
            const res = await fetch('/api/bedrock/inference-profiles');
            const data = await res.json();
            const profiles = Array.isArray(data.profiles) ? data.profiles : [];
            setBedrockInferenceProfiles(profiles);
        } catch {
            setBedrockInferenceProfiles([]);
        } finally {
            setLoadingInferenceProfiles(false);
        }
    };

    const handleSaveSection = async () => {
        await Promise.resolve(onSave(agentName, selectedModel, mode, {
            openai_key: openaiKey,
            anthropic_key: anthropicKey,
            gemini_key: geminiKey,
            bedrock_api_key: bedrockApiKey,
            google_maps_api_key: googleMapsApiKey,
            bedrock_inference_profile: bedrockInferenceProfile,
            aws_region: awsRegion,
            sql_connection_string: sqlConnectionString,
            n8n_url: n8nUrl,
            n8n_api_key: n8nApiKey,
            global_config: globalConfig.reduce((acc, curr) => {
                if (curr.key.trim()) acc[curr.key.trim()] = curr.value;
                return acc;
            }, {} as Record<string, string>),
            vault_enabled: vaultEnabled,
            vault_threshold: vaultThreshold,
            allow_db_write: allowDbWrite,
        }));

        if (mode === 'bedrock') {
            await refreshBedrockModels();
            await refreshBedrockInferenceProfiles();
        }
        setShowToast(true);
        setTimeout(() => setShowToast(false), 3000);
    };

    const handleSavePersonalDetails = async () => {
        try {
            const res = await fetch('/api/personal-details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    first_name: pdFirstName,
                    last_name: pdLastName,
                    email: pdEmail,
                    phone_number: pdPhone,
                    address: {
                        address1: pdAddress1,
                        address2: pdAddress2,
                        city: pdCity,
                        state: pdState,
                        zipcode: pdZipcode
                    }
                })
            });
            if (!res.ok) throw new Error('Failed to save personal details');
            setShowToast(true);
            setTimeout(() => setShowToast(false), 3000);
        } catch {
            alert('Error saving personal details.');
        }
    };

    // Fullscreen State
    const [isIframeFullscreen, setIsIframeFullscreen] = useState(false);
    const [n8nWorkflowId, setN8nWorkflowId] = useState<string | null>(null);
    const [isN8nLoading, setIsN8nLoading] = useState(true);
    const n8nIframeRef = useRef<HTMLIFrameElement>(null);

    // Reset n8n loading state when switching modes
    useEffect(() => {
        if (toolBuilderMode === 'n8n') {
            setIsN8nLoading(true);
        }
    }, [toolBuilderMode]);

    // Confirmation Modal State
    const [confirmAction, setConfirmAction] = useState<{ type: 'recent' | 'all', message: string } | null>(null);

    // Data Lab State
    const [dlTopic, setDlTopic] = useState('');
    const [dlCount, setDlCount] = useState(10);
    const [dlProvider, setDlProvider] = useState('openai');
    const [dlSystemPrompt, setDlSystemPrompt] = useState('You are a helpful assistant.');
    const [dlEdgeCases, setDlEdgeCases] = useState('');
    const [dlStatus, setDlStatus] = useState<any>(null);
    const [dlDatasets, setDlDatasets] = useState<any[]>([]);

    useEffect(() => {
        if (activeTab === 'datalab') {
            // Initial fetch
            fetchDatasets();
            fetchStatus();
            // Poll
            const interval = setInterval(() => {
                fetchStatus();
                if (dlStatus?.status === 'generating') fetchDatasets(); // Refresh list occasionally
            }, 2000);
            return () => clearInterval(interval);
        }
    }, [activeTab]);

    const fetchDatasets = () => fetch('/api/synthetic/datasets').then(r => r.json()).then(setDlDatasets).catch(() => { });
    const fetchStatus = () => fetch('/api/synthetic/status').then(r => r.json()).then(setDlStatus).catch(() => { });

    const getN8nBaseUrl = () => (n8nUrl || 'http://localhost:5678').replace(/\/+$/, '');

    const handleGenerateData = async () => {
        if (!dlTopic) return alert("Please enter a topic.");
        if (dlProvider === 'openai' && !openaiKey) return alert("OpenAI Key required.");
        if (dlProvider === 'gemini' && !geminiKey) return alert("Gemini Key required.");

        try {
            const res = await fetch('/api/synthetic/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic: dlTopic,
                    count: dlCount,
                    provider: dlProvider,
                    api_key: dlProvider === 'openai' ? openaiKey : geminiKey,
                    system_prompt: dlSystemPrompt,
                    edge_cases: dlEdgeCases
                })
            });
            if (res.ok) {
                alert("Generation Started!");
                fetchStatus();
            } else {
                const err = await res.json();
                alert("Error: " + err.detail);
            }
        } catch (e) {
            alert("Failed to start generation.");
        }
    };

    // History Handler - Open Modal
    const handleClearHistory = (type: 'recent' | 'all') => {
        const message = type === 'recent'
            ? "Are you sure you want to clear RECENT history? This only removes the current session's short-term memory."
            : "Are you sure you want to clear ALL history? This will permanently delete ALL long-term memories (ChromaDB) and the current session.";

        setConfirmAction({ type, message });
    };

    // Actual Execution
    const executeClearHistory = async () => {
        if (!confirmAction) return;

        try {
            const res = await fetch(`/api/history/${confirmAction.type}`, { method: 'DELETE' });
            if (res.ok) {
                alert(`${confirmAction.type === 'recent' ? 'Recent' : 'All'} history cleared successfully.`);
            } else {
                alert("Failed to clear history.");
            }
        } catch (e) {
            alert("Error clearing history.");
        } finally {
            setConfirmAction(null);
        }
    };

    // Close on escape
    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [onClose]);
    // Fetch data on open
    useEffect(() => {
        if (isOpen) {
            // Get settings
            fetch('/api/settings')
                .then(res => res.json())
                .then(data => {
                    setAgentName(data.agent_name || 'Antigravity Agent');
                    setSelectedModel(data.model || 'mistral');
                    setMode(data.mode || 'local');
                    setOpenaiKey(data.openai_key || '');
                    setAnthropicKey(data.anthropic_key || '');
                    setGeminiKey(data.gemini_key || '');
                    setBedrockApiKey(data.bedrock_api_key || '');
                    setGoogleMapsApiKey(data.google_maps_api_key || '');
                    setAwsRegion(data.aws_region || 'us-east-1');
                    setBedrockInferenceProfile(data.bedrock_inference_profile || '');
                    setSqlConnectionString(data.sql_connection_string || '');
                    setN8nUrl(data.n8n_url || 'http://localhost:5678');
                    setN8nApiKey(data.n8n_api_key || '');
                    setVaultEnabled(data.vault_enabled !== undefined ? data.vault_enabled : true);
                    setVaultThreshold(data.vault_threshold || 15000);
                    setAllowDbWrite(data.allow_db_write || false);
                    if (data.global_config) {
                         const configArray = Object.entries(data.global_config).map(([k, v]) => ({
                             id: Math.random().toString(36).substr(2, 9),
                             key: k,
                             value: v as string
                         }));
                         setGlobalConfig(configArray);
                    } else {
                        setGlobalConfig([]);
                    }
                });

            // Personal details
            fetch('/api/personal-details')
                .then(res => res.json())
                .then(data => {
                    setPdFirstName(data.first_name || '');
                    setPdLastName(data.last_name || '');
                    setPdEmail(data.email || '');
                    setPdPhone(data.phone_number || '');
                    const addr = data.address || {};
                    setPdAddress1(addr.address1 || '');
                    setPdAddress2(addr.address2 || '');
                    setPdCity(addr.city || '');
                    setPdState(addr.state || '');
                    setPdZipcode(addr.zipcode || '');
                })
                .catch(() => { });

            // Get models (provider-grouped)
            setLoadingModels(true);
            fetch('/api/models')
                .then(res => res.json())
                .then(data => {
                    setLocalModels(data.local || []);
                    setCloudModels(data.cloud || []);
                    if (data.providers) setProviders(data.providers);
                    setLoadingModels(false);
                })
                .catch(() => setLoadingModels(false));

            // Get Agents
            fetch('/api/agents')
                .then(res => res.json())
                .then(data => {
                    setAgents(Array.isArray(data) ? data : []);
                });

            // Get Custom Tools
            fetch('/api/tools/custom')
                .then(res => res.json())
                .then(data => {
                    setCustomTools(Array.isArray(data) ? data : []);
                });

            // Get Available Capabilities (Dynamic Tools + MCP)
            fetch('/api/tools/available')
                .then(res => res.json())
                .then(data => {
                    const tools = data.tools || [];
                    const groups: Record<string, any> = {};
                    
                    tools.forEach((t: any) => {
                        // Special handling for legacy custom tools: UNGROUP THEM
                        if (t.source === 'custom_http') {
                            const capId = t.name;
                            // avoid duplicate if same custom tool appears somehow
                            if (!groups[capId]) {
                                groups[capId] = {
                                    id: capId,
                                    label: t.label || t.name, // Use generalName if available
                                    description: t.description,
                                    tools: [t.name],
                                    toolDetails: [{ name: t.name, description: t.description || '' }],
                                    toolType: 'custom'
                                };
                            }
                        } else {
                            // Group by source (e.g., 'gmail', 'filesystem')
                            const source = t.source || 'unknown';
                            if (!groups[source]) {
                                groups[source] = {
                                    id: source,
                                    label: source.charAt(0).toUpperCase() + source.slice(1).replace(/_/g, ' '),
                                    description: `Tools from ${source}`,
                                    tools: [],
                                    toolDetails: [],
                                    /*
                                     * Determine tool type for badge:
                                     * - mcp_external -> 'mcp'
                                     * - mcp_native -> 'native' (no badge, but logic might say otherwise)
                                     * - custom_http -> 'custom' (handled above really, but safe fallback)
                                     */
                                    toolType: t.type === 'mcp_external' ? 'mcp' : (t.type === 'mcp_native' ? 'native' : 'custom')
                                };
                            }
                            groups[source].tools.push(t.name);
                            groups[source].toolDetails.push({ name: t.name, description: t.description || '' });
                        }
                    });
                    
                    const dynamicCaps = Object.values(groups);
                    const merged = dynamicCaps.map(cap => {
                        // Try to find matching static capability by ID (e.g. 'gmail')
                        const existing = CAPABILITIES.find(c => c.id === cap.id);
                        if (existing) {
                            return { ...cap, label: existing.label, description: existing.description, toolType: 'native' };
                        }
                        return cap;
                    });
                    
                    setAvailableCapabilities(merged);
                });
        }
    }, [isOpen]);

    // Refresh Bedrock models dynamically when switching into bedrock mode.
    useEffect(() => {
        if (!isOpen) return;
        if (mode !== 'bedrock') return;

        refreshBedrockModels();
        refreshBedrockInferenceProfiles();
    }, [isOpen, mode]);

    // Fetch n8n workflows when the Tool Builder is open (for dropdown)
    useEffect(() => {
        if (!isOpen) return;
        if (activeTab !== 'custom_tools') return;
        if (!draftTool) return;
        if (toolBuilderMode !== 'config') return;
        if (n8nWorkflows.length > 0) return;
        fetchN8nWorkflows();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, activeTab, draftTool, toolBuilderMode]);

    // Fetch MCP Servers
    useEffect(() => {
        if (isOpen && activeTab === 'mcp_servers') {
            fetchMcpServers();
        }
    }, [isOpen, activeTab]);

    const fetchMcpServers = async () => {
        setLoadingMcp(true);
        try {
            const res = await fetch('/api/mcp/servers');
            if (res.ok) {
                const data = await res.json();
                setMcpServers(Array.isArray(data) ? data : []);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoadingMcp(false);
        }
    };

    const handleAddMcpServer = async () => {
        if (!draftMcpServer.name || !draftMcpServer.command) {
            alert("Name and Command are required.");
            return;
        }
        
        const argsList = draftMcpServer.args.match(/(?:[^\s"]+|"[^"]*")+/g)?.map(s => s.replace(/^"|"$/g, '')) || [];
        
        const envObj = draftMcpServer.env.reduce((acc, curr) => {
            if (curr.key) acc[curr.key] = curr.value;
            return acc;
        }, {} as Record<string, string>);

        try {
            const res = await fetch('/api/mcp/servers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: draftMcpServer.name,
                    command: draftMcpServer.command,
                    args: argsList,
                    env: envObj
                })
            });
            if (res.ok) {
                await fetchMcpServers();
                setDraftMcpServer({ name: '', command: '', args: '', env: [] });
                alert("Server added successfully!");
            } else {
                const err = await res.json();
                alert(`Error adding server: ${err.detail || 'Unknown error'}`);
            }
        } catch (e) {
            alert("Failed to connect to server.");
        }
    };

    const handleDeleteMcpServer = async (name: string) => {
        if (!confirm(`Remove MCP server '${name}'?`)) return;
        try {
            const res = await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' });
            if (res.ok) {
                await fetchMcpServers();
            } else {
                alert("Failed to delete server.");
            }
        } catch (e) {
            alert("Error deleting server.");
        }
    };

    // Handle Save Custom Tool
    const handleSaveTool = async () => {
        if (!draftTool) return;
        // Validate
        if (!draftTool.name || !draftTool.url) {
            alert("Name and URL are required.");
            return;
        }

        // Validate Schemas
        let finalInputSchema = draftTool.inputSchema;
        let finalOutputSchema = draftTool.outputSchema;

        try {
            if (typeof draftTool.inputSchemaStr === 'string') {
                finalInputSchema = JSON.parse(draftTool.inputSchemaStr);
            }
        } catch (e) {
            alert("Invalid Input Schema JSON");
            return;
        }

        try {
            if (typeof draftTool.outputSchemaStr === 'string' && draftTool.outputSchemaStr.trim()) {
                finalOutputSchema = JSON.parse(draftTool.outputSchemaStr);
            } else if (!draftTool.outputSchemaStr || !draftTool.outputSchemaStr.trim()) {
                finalOutputSchema = undefined;
            }
        } catch (e) {
            alert("Invalid Output Schema JSON");
            return;
        }

        try {
            // Convert header rows to object
            const headersObj: Record<string, string> = {};
            headerRows.forEach(r => {
                if (r.key.trim()) headersObj[r.key.trim()] = r.value;
            });

            const payload = {
                ...draftTool,
                inputSchema: finalInputSchema,
                outputSchema: finalOutputSchema,
                headers: headersObj
            };

            // Clean up temporary fields
            delete payload.inputSchemaStr;
            delete payload.outputSchemaStr;

            const res = await fetch('/api/tools/custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                const savedResp = await res.json();
                const saved = savedResp?.tool ?? savedResp;
                // Refresh list
                const idx = customTools.findIndex((t: any) => t.name === draftTool.name);
                if (idx >= 0) {
                    const newTools = [...customTools];
                    newTools[idx] = saved;
                    setCustomTools(newTools);
                } else {
                    setCustomTools([...customTools, saved]);
                }
                setDraftTool(null);
                setToolBuilderMode('config');
                alert("Tool saved successfully!");
            } else {
                alert("Failed to save tool");
            }
        } catch (e) {
            alert("Error saving tool.");
        }
    };

    const fetchN8nWorkflows = async () => {
        if (n8nWorkflowsLoading) return;
        setN8nWorkflowsLoading(true);
        try {
            const res = await fetch('/api/n8n/workflows');
            if (!res.ok) {
                setN8nWorkflows([]);
                return;
            }
            const data = await res.json();
            setN8nWorkflows(Array.isArray(data) ? data : []);
        } catch {
            setN8nWorkflows([]);
        } finally {
            setN8nWorkflowsLoading(false);
        }
    };

    // Handle Delete Tool
    const handleDeleteTool = async (name: string) => {
        if (!confirm("Delete this tool?")) return;
        try {
            await fetch(`/api/tools/custom/${name}`, { method: 'DELETE' });
            setCustomTools(customTools.filter(t => t.name !== name));
        } catch (e) { alert("Error deleting tool"); }
    };

    // Handle Save Agent
    const handleSaveAgent = async () => {
        if (!draftAgent) return;

        try {
            const res = await fetch('/api/agents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(draftAgent)
            });
            if (res.ok) {
                const saved = await res.json();
                // Update local list
                const idx = agents.findIndex((a: any) => a.id === saved.id);
                if (idx >= 0) {
                    const newAgents = [...agents];
                    newAgents[idx] = saved;
                    setAgents(newAgents);
                } else {
                    setAgents([...agents, saved]);
                }
                alert("Agent saved successfully!");
            }
        } catch (e) {
            alert("Error saving agent.");
        }
    };

    // Handle Delete Agent
    const handleDeleteAgent = async (id: string) => {
        if (!confirm("Are you sure you want to delete this agent?")) return;
        try {
            await fetch(`/api/agents/${id}`, { method: 'DELETE' });
            setAgents(agents.filter((a: any) => a.id !== id));
            if (selectedAgentId === id) {
                setSelectedAgentId(null);
                setDraftAgent(null);
            }
        } catch (e) {
            alert("Error deleting agent");
        }
    };


    if (!isOpen) return null;

    // Filter models based on mode
    const filteredModels = mode === 'local'
        ? localModels
        : (mode === 'bedrock' ? cloudModels.filter(m => m.startsWith('bedrock')) : cloudModels.filter(m => !m.startsWith('bedrock')));

    const tabs = [
        { id: 'general', label: 'General', icon: LayoutGrid },
        { id: 'personal_details', label: 'Personal Details', icon: Shield },
        { id: 'orchestrations', label: 'Orchestrations', icon: Workflow },
        { id: 'agents', label: 'Build Agents', icon: Bot },
        { id: 'mcp_servers', label: 'MCP Servers', icon: Server },
        { id: 'custom_tools', label: 'Tool Builder', icon: Wrench },
        { id: 'repos', label: 'Repos', icon: FolderGit2 },
        { id: 'db_configs', label: 'DB Configs', icon: Database },
        { id: 'models', label: 'Models', icon: Cpu },
        { id: 'workspace', label: 'Integrations', icon: Cloud },
        { id: 'memory', label: 'Memory', icon: Trash },
        { id: 'logs', label: 'Logs', icon: ScrollText },
    ];

    // Added font-mono to ensure inheritance if not already inherited
    return (
        <>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-md animate-in fade-in duration-200 font-mono">
                <div className="w-full h-full bg-black shadow-2xl flex flex-col md:flex-row overflow-hidden relative">

                    {/* Header (Mobile) / Close Button */}
                    <button
                        onClick={onClose}
                        className="absolute top-4 right-4 z-50 p-2 text-zinc-500 hover:text-white hover:bg-zinc-900 transition-colors"
                    >
                        <X className="h-6 w-6" />
                    </button>

                    {/* Sidebar */}
                    <div className="w-full md:w-64 bg-zinc-950 border-b md:border-b-0 md:border-r border-white/10 flex flex-col shrink-0">
                        <div className="p-6 border-b border-white/10 md:mb-2">
                            <h2 className="text-xl font-bold flex items-center gap-3 tracking-wider">
                                <Settings className="h-5 w-5 text-white" />
                                SETTINGS
                            </h2>
                        </div>

                        <nav className="flex-1 p-2 space-y-1 overflow-x-auto md:overflow-visible flex md:flex-col">
                            {tabs.map((tab) => {
                                const Icon = tab.icon;
                                const isActive = activeTab === tab.id;
                                return (
                                    <button
                                        key={tab.id}
                                        onClick={() => setActiveTab(tab.id as Tab)}
                                        // FIXED: Reduced padding (py-3 -> py-2.5) and removed translate-x-1 to fix misalignment
                                        className={`flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-all duration-200 whitespace-nowrap md:whitespace-normal
                                            ${isActive
                                                ? 'bg-white text-black shadow-lg'
                                                : 'text-zinc-400 hover:text-white hover:bg-white/5'
                                            }`}
                                    >
                                        <Icon className={`h-4 w-4 ${isActive ? 'text-black' : 'text-zinc-500 group-hover:text-white'}`} />
                                        {tab.label}
                                    </button>
                                );
                            })}
                        </nav>

                        <div className="p-4 border-t border-white/10 hidden md:block">
                            <div className="text-[10px] text-zinc-600 font-mono text-center">
                                Synapse v1.0
                            </div>
                        </div>
                    </div>

                    {/* Main Content Area */}
                    {/* FIXED: Changed bg-black/50 to bg-transparent to allow parent bg-black (which inverts properly) to show through. */}
                    <div className="flex-1 flex flex-col h-full overflow-hidden bg-transparent">
                        {/* Orchestrations tab: full-bleed layout, no scroll wrapper */}
                        {activeTab === 'orchestrations' && (
                            <div className="flex-1 flex flex-col overflow-hidden">
                                <OrchestrationTab />
                            </div>
                        )}

                        {/* Logs tab: full-bleed two-pane layout */}
                        {activeTab === 'logs' && (
                            <div className="flex-1 flex flex-col overflow-hidden">
                                <LogsTab />
                            </div>
                        )}

                        <div className={`flex-1 overflow-y-auto p-6 md:p-12 ${activeTab === 'orchestrations' || activeTab === 'logs' ? 'hidden' : ''}`}>
                            <div className="max-w-5xl mx-auto space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-300">

                                <div className="mb-8">
                                    <h1 className="text-3xl font-bold mb-2">{tabs.find(t => t.id === activeTab)?.label}</h1>
                                    <p className="text-zinc-500 text-sm">Manage your agent's {activeTab} configuration.</p>
                                </div>

                                {/* GENERAL TAB */}
                                {activeTab === 'general' && (
                                    <GeneralTab
                                        agentName={agentName}
                                        setAgentName={setAgentName}
                                        vaultEnabled={vaultEnabled}
                                        setVaultEnabled={setVaultEnabled}
                                        vaultThreshold={vaultThreshold}
                                        setVaultThreshold={setVaultThreshold}
                                        allowDbWrite={allowDbWrite}
                                        setAllowDbWrite={setAllowDbWrite}
                                        onSave={handleSaveSection}
                                    />
                                )}

                                {/* PERSONAL DETAILS TAB */}
                                {activeTab === 'personal_details' && (
                                    <PersonalDetailsTab
                                        pdFirstName={pdFirstName} setPdFirstName={setPdFirstName}
                                        pdLastName={pdLastName} setPdLastName={setPdLastName}
                                        pdEmail={pdEmail} setPdEmail={setPdEmail}
                                        pdPhone={pdPhone} setPdPhone={setPdPhone}
                                        pdAddress1={pdAddress1} setPdAddress1={setPdAddress1}
                                        pdAddress2={pdAddress2} setPdAddress2={setPdAddress2}
                                        pdCity={pdCity} setPdCity={setPdCity}
                                        pdState={pdState} setPdState={setPdState}
                                        pdZipcode={pdZipcode} setPdZipcode={setPdZipcode}
                                        onSave={handleSavePersonalDetails}
                                    />
                                )}

                                {/* AGENTS TAB */}
                                {activeTab === 'agents' && (
                                    <AgentsTab
                                        agents={agents}
                                        selectedAgentId={selectedAgentId}
                                        setSelectedAgentId={setSelectedAgentId}
                                        draftAgent={draftAgent}
                                        setDraftAgent={setDraftAgent}
                                        availableCapabilities={availableCapabilities}
                                        customTools={customTools}
                                        onSaveAgent={handleSaveAgent}
                                        onDeleteAgent={handleDeleteAgent}
                                        providers={providers}
                                        defaultModel={selectedModel}
                                    />
                                )}



                                {/* CUSTOM TOOLS TAB */}
                                {activeTab === 'custom_tools' && (
                                    <CustomToolsTab
                                        customTools={customTools}
                                        draftTool={draftTool}
                                        setDraftTool={setDraftTool}
                                        toolBuilderMode={toolBuilderMode}
                                        setToolBuilderMode={setToolBuilderMode}
                                        headerRows={headerRows}
                                        setHeaderRows={setHeaderRows}
                                        n8nWorkflows={n8nWorkflows}
                                        n8nWorkflowsLoading={n8nWorkflowsLoading}
                                        n8nWorkflowId={n8nWorkflowId}
                                        setN8nWorkflowId={setN8nWorkflowId}
                                        isIframeFullscreen={isIframeFullscreen}
                                        setIsIframeFullscreen={setIsIframeFullscreen}
                                        isN8nLoading={isN8nLoading}
                                        setIsN8nLoading={setIsN8nLoading}
                                        n8nIframeRef={n8nIframeRef}
                                        getN8nBaseUrl={getN8nBaseUrl}
                                        onSaveTool={handleSaveTool}
                                        onDeleteTool={handleDeleteTool}
                                    />
                                )}

                                {/* DATA LAB TAB */}
                                {activeTab === 'datalab' && (
                                    <DataLabTab
                                        dlTopic={dlTopic} setDlTopic={setDlTopic}
                                        dlCount={dlCount} setDlCount={setDlCount}
                                        dlProvider={dlProvider} setDlProvider={setDlProvider}
                                        dlSystemPrompt={dlSystemPrompt} setDlSystemPrompt={setDlSystemPrompt}
                                        dlEdgeCases={dlEdgeCases} setDlEdgeCases={setDlEdgeCases}
                                        dlStatus={dlStatus}
                                        dlDatasets={dlDatasets}
                                        onGenerate={handleGenerateData}
                                    />
                                )}

                                {/* MODELS TAB */}
                                {activeTab === 'models' && (
                                    <ModelsTab
                                        providers={providers}
                                        mode={mode} setMode={setMode}
                                        selectedModel={selectedModel} setSelectedModel={setSelectedModel}
                                        localModels={localModels} cloudModels={cloudModels}
                                        filteredModels={filteredModels}
                                        loadingModels={loadingModels}
                                        openaiKey={openaiKey} setOpenaiKey={setOpenaiKey}
                                        anthropicKey={anthropicKey} setAnthropicKey={setAnthropicKey}
                                        geminiKey={geminiKey} setGeminiKey={setGeminiKey}
                                        bedrockApiKey={bedrockApiKey} setBedrockApiKey={setBedrockApiKey}
                                        awsRegion={awsRegion} setAwsRegion={setAwsRegion}
                                        bedrockInferenceProfile={bedrockInferenceProfile}
                                        setBedrockInferenceProfile={setBedrockInferenceProfile}
                                        bedrockInferenceProfiles={bedrockInferenceProfiles}
                                        loadingInferenceProfiles={loadingInferenceProfiles}
                                        onSave={handleSaveSection}
                                    />
                                )}

                                {/* INTEGRATIONS TAB */}
                                {activeTab === 'workspace' && (
                                    <IntegrationsTab
                                        n8nUrl={n8nUrl} setN8nUrl={setN8nUrl}
                                        n8nApiKey={n8nApiKey} setN8nApiKey={setN8nApiKey}
                                        googleMapsApiKey={googleMapsApiKey} setGoogleMapsApiKey={setGoogleMapsApiKey}
                                        globalConfig={globalConfig} setGlobalConfig={setGlobalConfig}
                                        onSave={handleSaveSection}
                                    />
                                )}

                                {/* MCP SERVERS TAB */}
                                {activeTab === 'mcp_servers' && (
                                    <McpServersTab
                                        mcpServers={mcpServers}
                                        loadingMcp={loadingMcp}
                                        draftMcpServer={draftMcpServer}
                                        setDraftMcpServer={setDraftMcpServer}
                                        onAddServer={handleAddMcpServer}
                                        onDeleteServer={handleDeleteMcpServer}
                                    />
                                )}

                                {/* MEMORY TAB */}
                                {activeTab === 'memory' && (
                                    <MemoryTab onClearHistory={handleClearHistory} />
                                )}

                                {/* REPOS TAB */}
                                {activeTab === 'repos' && (
                                    <ReposTab />
                                )}

                                {/* DB CONFIGS TAB */}
                                {activeTab === 'db_configs' && (
                                    <DBsTab />
                                )}
                            </div>
                        </div>

                        {/* Footer Content Actions */}
                        {/* FIXED: Changed bg-black/50 to bg-zinc-950 for consistent solid background */}
                        {/* Footer Removed - Per-section save applied */}
                    </div>
                </div>
            </div >

            {/* Toast Notification */}
            <ToastNotification show={showToast} />

            {/* Custom Confirmation Modal */}
            <ConfirmationModal
                confirmAction={confirmAction}
                setConfirmAction={setConfirmAction}
                onConfirm={executeClearHistory}
            />

            {/* Fullscreen n8n Iframe Overlay - Rendered outside modal to avoid clipping */}
            <N8nFullscreenOverlay
                isIframeFullscreen={isIframeFullscreen}
                toolBuilderMode={toolBuilderMode}
                draftTool={draftTool}
                setIsIframeFullscreen={setIsIframeFullscreen}
                getN8nBaseUrl={getN8nBaseUrl}
            />
        </>
    );
};
