/* eslint-disable @typescript-eslint/no-explicit-any */

export interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (name: string, model: string, mode: string, keys: any) => void | Promise<void>;
    credentials?: any;
}

export type Tab = 'general' | 'models' | 'workspace' | 'memory' | 'agents' | 'orchestrations' | 'datalab' | 'custom_tools' | 'personal_details' | 'mcp_servers' | 'repos' | 'db_configs' | 'logs' | 'messaging' | 'usage';

// Tools auto-injected by the backend per agent type.
// Shown as 'DEFAULT' in the UI and not editable.
export const AUTO_TOOLS_BY_TYPE: Record<string, string[]> = {
    all_types: ['query_past_conversations', 'sequentialthinking', 'read_file_chunk', 'search_file', 'read_json_chunk', 'search_json', 'grep', 'glob'],
    code: ['search_codebase'],
    orchestrator: [],
};

// Static tool group definitions for native Python agents.
// MCP-based tools (filesystem, playwright, google_workspace) are discovered dynamically
// from /api/tools/available and merged automatically.
export const CAPABILITIES = [
];
