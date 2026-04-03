/* eslint-disable @typescript-eslint/no-explicit-any */

export interface OrchestrationType {
  id: string;
  name: string;
  description?: string;
  steps?: Array<{ agent_id?: string }>;
}

export interface AgentType {
  id: string;
  name: string;
  description?: string;
  tools?: string[];
}

export interface McpServerType {
  name: string;
  label?: string;
  server_type?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  token?: string;
}

export interface CustomToolType {
  name: string;
  generalName?: string;
  description?: string;
  tool_type?: string;
  headers?: Record<string, string>;
}

export interface ExportData {
  orchestrations: OrchestrationType[];
  agents: AgentType[];
  mcp_servers: McpServerType[];
  custom_tools: CustomToolType[];
}

export interface ImportBundle {
  synapse_export: boolean;
  version?: string;
  exported_at?: string;
  has_python_tools?: boolean;
  orchestrations: OrchestrationType[];
  agents: AgentType[];
  mcp_servers: McpServerType[];
  custom_tools: CustomToolType[];
}

export interface ImportResult {
  id?: string;
  name?: string;
  label?: string;
  status: "imported" | "skipped_existing" | "error";
  message?: string;
}
