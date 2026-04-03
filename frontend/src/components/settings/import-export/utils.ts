import type { OrchestrationType, AgentType, McpServerType, CustomToolType } from "./types";

export function orchAgentDeps(orch: OrchestrationType): string[] {
  return (orch.steps || []).map(s => s.agent_id).filter(Boolean) as string[];
}

export function agentMcpDeps(agent: AgentType, allMcp: McpServerType[]): string[] {
  const tools = agent.tools || [];
  return allMcp.filter(m => tools.some(t => t.startsWith(`${m.name}__`))).map(m => m.name);
}

export function agentToolDeps(agent: AgentType, allTools: CustomToolType[]): string[] {
  return allTools.filter(t => (agent.tools || []).includes(t.name)).map(t => t.name);
}
