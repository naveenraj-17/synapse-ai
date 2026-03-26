/* eslint-disable @typescript-eslint/no-explicit-any */

export interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (name: string, model: string, mode: string, keys: any) => void | Promise<void>;
    credentials?: any;
}

export type Tab = 'general' | 'models' | 'workspace' | 'memory' | 'agents' | 'orchestrations' | 'datalab' | 'custom_tools' | 'personal_details' | 'mcp_servers' | 'repos' | 'db_configs' | 'logs';

// Tools auto-injected by the backend per agent type.
// Shown as "DEFAULT" in the UI and not editable.
export const AUTO_TOOLS_BY_TYPE: Record<string, string[]> = {
    all_types: ['query_past_conversations'],
    analysis: ['decide_search_or_analyze', 'search_embedded_report', 'embed_report_for_exploration'],
    code: ['search_codebase', 'grep', 'glob'],
    orchestrator: [],
};

// Helper text per agent type for the type dropdown.
export const AGENT_TYPE_DESCRIPTIONS: Record<string, string> = {
    conversational: 'General-purpose agent with configurable tools.',
    analysis: 'Automatically includes RAG/embedding tools for data exploration.',
    workflow: 'For orchestration workflows (LangGraph integration planned).',
    code: 'Automatically includes search_codebase for semantic code search.',
    orchestrator: 'Multi-agent orchestration — deployed from the Orchestrations tab.',
};

// Static tool group definitions for native Python agents.
// MCP-based tools (filesystem, playwright, google_workspace) are discovered dynamically
// from /api/tools/available and merged automatically.
export const CAPABILITIES = [
    {
        id: 'maps',
        label: 'Google Maps',
        description: 'Distance, duration, and directions link between two points.',
        tools: ['get_map_details'],
        toolDetails: [{ name: 'get_map_details', description: 'Get distance, duration, and directions between two points' }]
    },
    {
        id: 'sql',
        label: 'SQL Database',
        description: 'Query business database (Tables, SQL).',
        tools: ['list_tables', 'get_table_schema', 'run_sql_query'],
        toolDetails: [
            { name: 'list_tables', description: 'List all available database tables' },
            { name: 'get_table_schema', description: 'Get the schema of a database table' },
            { name: 'run_sql_query', description: 'Execute a SQL query on the database' }
        ]
    },
    {
        id: 'datetime',
        label: 'Date & Time',
        description: 'Get current and future dates with natural language.',
        tools: ['get_datetime'],
        toolDetails: [{ name: 'get_datetime', description: 'Get current and future dates' }]
    },
    {
        id: 'personal_details',
        label: 'Personal Details',
        description: 'Get saved personal info (name, phone, address).',
        tools: ['get_personal_details'],
        toolDetails: [{ name: 'get_personal_details', description: 'Get saved personal information' }]
    },
    {
        id: 'pdf_parser',
        label: 'PDF Parser',
        description: 'Parse content from PDF files via URL.',
        tools: ['parse_pdf'],
        toolDetails: [{ name: 'parse_pdf', description: 'Parse content from PDF files via URL' }]
    },
    {
        id: 'xlsx_parser',
        label: 'Excel Parser',
        description: 'Parse content from Excel (XLSX) files via URL.',
        tools: ['parse_xlsx'],
        toolDetails: [{ name: 'parse_xlsx', description: 'Parse content from Excel files via URL' }]
    },
    {
        id: 'collect_data',
        label: 'Data Collection Forms',
        description: 'Collect structured data from users via interactive forms.',
        tools: ['collect_data'],
        toolDetails: [{ name: 'collect_data', description: 'Request structured user input via form fields (text, number, email, date, etc.)' }]
    }
];
