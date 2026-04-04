/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Upload, Package, CheckCircle2, AlertTriangle,
  SkipForward, XCircle, Workflow, Bot, Server, Wrench,
  AlertCircle, Loader2,
} from "lucide-react";
import type { ImportBundle, ImportResult, OrchestrationType, AgentType, McpServerType, CustomToolType } from "./types";
import { orchAgentDeps, agentMcpDeps, agentToolDeps } from "./utils";
import { SectionTable } from "./SectionTable";

const inputCls = "w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700";

type ImportStep = "upload" | "preview" | "secrets" | "results";

export function ImportView({ preloadedBundle, onReset }: {
  preloadedBundle?: any;
  onReset?: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [step, setStep] = useState<ImportStep>("upload");
  const [bundle, setBundle] = useState<ImportBundle | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const [selOrch, setSelOrch] = useState<Set<string>>(new Set());
  const [selAgent, setSelAgent] = useState<Set<string>>(new Set());
  const [selMcp, setSelMcp] = useState<Set<string>>(new Set());
  const [selTool, setSelTool] = useState<Set<string>>(new Set());
  const [lockedAgent, setLockedAgent] = useState<Set<string>>(new Set());
  const [lockedMcp, setLockedMcp] = useState<Set<string>>(new Set());
  const [lockedTool, setLockedTool] = useState<Set<string>>(new Set());

  const [mcpSecrets, setMcpSecrets] = useState<Record<string, Record<string, string>>>({});
  const [toolSecrets, setToolSecrets] = useState<Record<string, Record<string, string>>>({});
  const [results, setResults] = useState<Record<string, ImportResult[]>>({});

  // Refs for always-current selection state — same pattern as bundleRef.
  // Used to avoid stale closures in toggle handlers without calling setState inside state updaters.
  const bundleRef = useRef<ImportBundle | null>(null);
  bundleRef.current = bundle;

  const selOrchRef = useRef<Set<string>>(selOrch);
  selOrchRef.current = selOrch;

  const selAgentRef = useRef<Set<string>>(selAgent);
  selAgentRef.current = selAgent;

  // Auto-parse a bundle that was pushed from ExamplesView
  useEffect(() => {
    if (!preloadedBundle) return;
    try {
      if (!preloadedBundle.synapse_export) throw new Error("Not a valid Synapse export file.");
      setBundle(preloadedBundle);
      setParseError(null);
      const orchIds = new Set<string>((preloadedBundle.orchestrations || []).map((o: OrchestrationType) => o.id));
      const agentIds = new Set<string>((preloadedBundle.agents || []).map((a: AgentType) => a.id));
      const mcpNames = new Set<string>((preloadedBundle.mcp_servers || []).map((m: McpServerType) => m.name));
      const toolNames = new Set<string>((preloadedBundle.custom_tools || []).map((t: CustomToolType) => t.name));
      setSelOrch(orchIds); setSelAgent(agentIds); setSelMcp(mcpNames); setSelTool(toolNames);
      const ms: Record<string, Record<string, string>> = {};
      for (const m of preloadedBundle.mcp_servers || []) {
        if (m.env && Object.keys(m.env).length > 0)
          ms[m.name] = Object.fromEntries(Object.keys(m.env).map((k: string) => [k, ""]));
      }
      setMcpSecrets(ms);
      const ts: Record<string, Record<string, string>> = {};
      for (const t of preloadedBundle.custom_tools || []) {
        if (t.headers && Object.keys(t.headers).length > 0)
          ts[t.name] = Object.fromEntries(Object.keys(t.headers).map((k: string) => [k, ""]));
      }
      setToolSecrets(ts);
      recalcImport(orchIds, agentIds, preloadedBundle);
      setStep("preview");
    } catch (err: any) { setParseError(err.message); }
  // Only run when preloadedBundle changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preloadedBundle]);


  const recalcImport = useCallback((newSelOrch: Set<string>, newSelAgent: Set<string>, b: ImportBundle) => {
    const orchLockedAgents = new Set<string>();
    for (const oid of newSelOrch) {
      const o = b.orchestrations?.find(x => x.id === oid);
      if (o) orchAgentDeps(o).forEach(a => orchLockedAgents.add(a));
    }
    const allAgents = new Set([...newSelAgent, ...orchLockedAgents]);
    const agentLockedMcp = new Set<string>();
    const agentLockedTool = new Set<string>();
    for (const aid of allAgents) {
      const ag = b.agents?.find(a => a.id === aid);
      if (ag) {
        agentMcpDeps(ag, b.mcp_servers || []).forEach(m => agentLockedMcp.add(m));
        agentToolDeps(ag, b.custom_tools || []).forEach(t => agentLockedTool.add(t));
      }
    }
    setLockedAgent(orchLockedAgents);
    setLockedMcp(agentLockedMcp);
    setLockedTool(agentLockedTool);
    setSelAgent(prev => new Set([...prev, ...orchLockedAgents]));
    setSelMcp(prev => new Set([...prev, ...agentLockedMcp]));
    setSelTool(prev => new Set([...prev, ...agentLockedTool]));
  }, []);

  const parseFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const parsed = JSON.parse(e.target?.result as string);
        if (!parsed.synapse_export) throw new Error("Not a valid Synapse export file.");
        setBundle(parsed);
        setParseError(null);
        const orchIds = new Set<string>((parsed.orchestrations || []).map((o: OrchestrationType) => o.id));
        const agentIds = new Set<string>((parsed.agents || []).map((a: AgentType) => a.id));
        const mcpNames = new Set<string>((parsed.mcp_servers || []).map((m: McpServerType) => m.name));
        const toolNames = new Set<string>((parsed.custom_tools || []).map((t: CustomToolType) => t.name));
        setSelOrch(orchIds); setSelAgent(agentIds); setSelMcp(mcpNames); setSelTool(toolNames);
        const ms: Record<string, Record<string, string>> = {};
        for (const m of parsed.mcp_servers || []) {
          if (m.env && Object.keys(m.env).length > 0)
            ms[m.name] = Object.fromEntries(Object.keys(m.env).map((k: string) => [k, ""]));
        }
        setMcpSecrets(ms);
        const ts: Record<string, Record<string, string>> = {};
        for (const t of parsed.custom_tools || []) {
          if (t.headers && Object.keys(t.headers).length > 0)
            ts[t.name] = Object.fromEntries(Object.keys(t.headers).map((k: string) => [k, ""]));
        }
        setToolSecrets(ts);
        recalcImport(orchIds, agentIds, parsed);
        setStep("preview");
      } catch (err: any) { setParseError(err.message); }
    };
    reader.readAsText(file);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    file && file.name.endsWith(".json") ? parseFile(file) : setParseError("Please drop a .json file.");
  }, []);

  const reset = () => {
    setStep("upload"); setBundle(null); setParseError(null); setResults({});
    setSelOrch(new Set()); setSelAgent(new Set()); setSelMcp(new Set()); setSelTool(new Set());
    setLockedAgent(new Set()); setLockedMcp(new Set()); setLockedTool(new Set());
    setMcpSecrets({}); setToolSecrets({});
    onReset?.();
  };

  const needsSecrets = bundle && (
    [...selMcp].some(n => { const m = bundle.mcp_servers.find(x => x.name === n); return m?.env && Object.keys(m.env).length > 0; }) ||
    [...selTool].some(n => { const t = bundle.custom_tools.find(x => x.name === n); return t?.headers && Object.keys(t.headers).length > 0; })
  );

  const handleImport = async () => {
    if (!bundle) return;
    setImporting(true);
    try {
      const res = await fetch("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bundle, mcp_secrets: mcpSecrets, tool_secrets: toolSecrets, selected_orchestration_ids: [...selOrch], selected_agent_ids: [...selAgent], selected_mcp_server_names: [...selMcp], selected_custom_tool_names: [...selTool] }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Import failed");
      setResults(data.results || {}); setStep("results");
    } catch (e: any) { setParseError(e.message); }
    finally { setImporting(false); }
  };

  // ── Upload ────────────────────────────────────────────────────────────────
  if (step === "upload") return (
    <div className="space-y-4">
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        className={`flex flex-col items-center justify-center border border-dashed py-14 px-8 cursor-pointer transition-colors ${dragging ? "border-white bg-zinc-800" : "border-zinc-700 bg-zinc-900/30 hover:border-zinc-500 hover:bg-zinc-900/60"}`}
      >
        <Upload className="h-8 w-8 text-zinc-600 mb-3" />
        <p className="text-zinc-300 text-sm font-bold">Drop your export file here</p>
        <p className="text-zinc-600 text-xs mt-1">or click to browse · JSON files only</p>
        <input ref={fileRef} type="file" accept=".json" className="sr-only" onChange={e => { const f = e.target.files?.[0]; if (f) parseFile(f); e.target.value = ""; }} />
      </div>
      {parseError && (
        <div className="flex items-center gap-2 text-red-400 text-xs p-3 border border-red-900/50 bg-red-950/10">
          <XCircle className="h-4 w-4 flex-shrink-0" /> {parseError}
        </div>
      )}
    </div>
  );

  // ── Preview ───────────────────────────────────────────────────────────────
  if (step === "preview" && bundle) {
    const total = selOrch.size + selAgent.size + selMcp.size + selTool.size;
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-3 px-4 py-3 border border-zinc-800 bg-zinc-900">
          <Package className="h-4 w-4 text-zinc-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-zinc-200">Bundle loaded</p>
            <p className="text-[10px] text-zinc-600 font-mono">
              v{bundle.version || "1.0"} · {bundle.exported_at ? new Date(bundle.exported_at).toLocaleString() : "unknown date"}
            </p>
          </div>
          <button onClick={reset} className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors underline underline-offset-2">Change file</button>
        </div>

        {bundle.has_python_tools && (
          <div className="flex items-start gap-3 p-4 border border-yellow-900/50 bg-yellow-950/10">
            <AlertTriangle className="h-4 w-4 text-yellow-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-yellow-400 text-xs font-bold uppercase tracking-wider">Python Tools Included</p>
              <p className="text-yellow-600 text-xs mt-1">Review all Python tool code carefully for hardcoded secrets before importing.</p>
            </div>
          </div>
        )}

        <div className="border border-zinc-800 divide-y divide-zinc-800">
          <SectionTable
            title="Orchestrations" icon={Workflow}
            items={bundle.orchestrations || []}
            selected={selOrch} locked={new Set()}
            getId={o => o.id} getLabel={o => o.name} getDesc={o => o.description}
            onToggle={(id, checked) => {
              const next = new Set(selOrchRef.current);
              checked ? next.add(id) : next.delete(id);
              setSelOrch(next);
              if (bundleRef.current) recalcImport(next, selAgentRef.current, bundleRef.current);
            }}
          />
          <SectionTable
            title="Agents" icon={Bot}
            items={bundle.agents || []}
            selected={selAgent} locked={lockedAgent}
            getId={a => a.id} getLabel={a => a.name} getDesc={a => a.description}
            onToggle={(id, checked) => {
              if (lockedAgent.has(id)) return;
              const next = new Set(selAgentRef.current);
              checked ? next.add(id) : next.delete(id);
              setSelAgent(next);
              if (bundleRef.current) recalcImport(selOrchRef.current, next, bundleRef.current);
            }}
          />
          <SectionTable
            title="MCP Servers" icon={Server}
            items={bundle.mcp_servers || []}
            selected={selMcp} locked={lockedMcp}
            getId={m => m.name} getLabel={m => m.label || m.name}
            onToggle={(name, checked) => {
              if (lockedMcp.has(name)) return;
              setSelMcp(prev => { const n = new Set(prev); checked ? n.add(name) : n.delete(name); return n; });
            }}
          />
          <SectionTable
            title="Custom Tools" icon={Wrench}
            items={bundle.custom_tools || []}
            selected={selTool} locked={lockedTool}
            getId={t => t.name} getLabel={t => t.generalName || t.name} getDesc={t => t.description}
            onToggle={(name, checked) => {
              if (lockedTool.has(name)) return;
              setSelTool(prev => { const n = new Set(prev); checked ? n.add(name) : n.delete(name); return n; });
            }}
          />
        </div>

        <div className="flex items-center justify-between gap-4 pt-2">
          <button onClick={reset} className="px-4 py-2 text-sm font-bold border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white transition-colors">
            Cancel
          </button>
          <button
            disabled={total === 0}
            onClick={() => needsSecrets ? setStep("secrets") : handleImport()}
            className="flex items-center gap-2 px-6 py-2 bg-white text-black text-sm font-bold hover:bg-zinc-200 transition-colors disabled:opacity-40"
          >
            {needsSecrets ? "Configure Secrets →" : <><Upload className="h-4 w-4" /> Import Now</>}
          </button>
        </div>
        {parseError && <p className="text-red-400 text-xs">{parseError}</p>}
      </div>
    );
  }

  // ── Secrets ───────────────────────────────────────────────────────────────
  if (step === "secrets" && bundle) {
    const relevantMcp = bundle.mcp_servers.filter(m => selMcp.has(m.name) && m.env && Object.keys(m.env).length > 0);
    const relevantTools = bundle.custom_tools.filter(t => selTool.has(t.name) && t.tool_type !== "python" && t.headers && Object.keys(t.headers).length > 0);

    return (
      <div className="space-y-6">
        <div className="flex items-start gap-3 p-4 border border-blue-900/50 bg-blue-950/10">
          <AlertCircle className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-blue-400 text-xs font-bold uppercase tracking-wider">Secret Values Required</p>
            <p className="text-blue-600 text-xs mt-1">MCP server env vars and custom tool headers were redacted during export. Enter the actual values before importing.</p>
          </div>
        </div>

        {relevantMcp.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 flex items-center gap-2">
              <Server className="h-3 w-3" /> MCP Server Environment Variables
            </h4>
            {relevantMcp.map(m => (
              <div key={m.name} className="border border-zinc-800">
                <div className="px-4 py-2.5 bg-zinc-900 flex items-center gap-2">
                  <span className="text-sm font-bold text-zinc-200">{m.label || m.name}</span>
                  <span className="text-[10px] text-zinc-600 font-mono">{m.name}</span>
                </div>
                <div className="p-4 space-y-3">
                  {Object.keys(m.env || {}).map(key => (
                    <div key={key} className="flex items-center gap-3">
                      <label className="text-[10px] uppercase font-bold text-zinc-600 font-mono w-36 flex-shrink-0 truncate">{key}</label>
                      <input
                        type="password"
                        value={mcpSecrets[m.name]?.[key] || ""}
                        onChange={e => setMcpSecrets(prev => ({ ...prev, [m.name]: { ...(prev[m.name] || {}), [key]: e.target.value } }))}
                        placeholder={`Value for ${key}`}
                        className={`${inputCls} flex-1 font-mono`}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {relevantTools.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 flex items-center gap-2">
              <Wrench className="h-3 w-3" /> Custom Tool Headers
            </h4>
            {relevantTools.map(t => (
              <div key={t.name} className="border border-zinc-800">
                <div className="px-4 py-2.5 bg-zinc-900 flex items-center gap-2">
                  <span className="text-sm font-bold text-zinc-200">{t.generalName || t.name}</span>
                  <span className="text-[10px] text-zinc-600 font-mono">{t.name}</span>
                </div>
                <div className="p-4 space-y-3">
                  {Object.keys(t.headers || {}).map(key => (
                    <div key={key} className="flex items-center gap-3">
                      <label className="text-[10px] uppercase font-bold text-zinc-600 font-mono w-36 flex-shrink-0 truncate">{key}</label>
                      <input
                        type="password"
                        value={toolSecrets[t.name]?.[key] || ""}
                        onChange={e => setToolSecrets(prev => ({ ...prev, [t.name]: { ...(prev[t.name] || {}), [key]: e.target.value } }))}
                        placeholder={`Value for ${key}`}
                        className={`${inputCls} flex-1 font-mono`}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between gap-4 pt-2">
          <button onClick={() => setStep("preview")} className="px-4 py-2 text-sm font-bold border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white transition-colors">
            ← Back
          </button>
          <button
            disabled={importing}
            onClick={handleImport}
            className="flex items-center gap-2 px-6 py-2 bg-white text-black text-sm font-bold hover:bg-zinc-200 transition-colors disabled:opacity-50"
          >
            {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {importing ? "Importing…" : "Start Import"}
          </button>
        </div>
        {parseError && <p className="text-red-400 text-xs">{parseError}</p>}
      </div>
    );
  }

  // ── Results ───────────────────────────────────────────────────────────────
  if (step === "results") {
    const all = Object.values(results).flat();
    const importedCount = all.filter(r => r.status === "imported").length;
    const groups = [
      { key: "orchestrations", label: "Orchestrations", icon: Workflow },
      { key: "agents", label: "Agents", icon: Bot },
      { key: "mcp_servers", label: "MCP Servers", icon: Server },
      { key: "custom_tools", label: "Custom Tools", icon: Wrench },
    ] as const;

    return (
      <div className="space-y-5">
        <div className="flex items-center gap-3 px-4 py-3 border border-green-900/50 bg-green-950/10">
          <CheckCircle2 className="h-4 w-4 text-green-400 flex-shrink-0" />
          <div>
            <p className="text-green-400 text-xs font-bold uppercase tracking-wider">Import Complete</p>
            <p className="text-green-700 text-xs mt-0.5">
              {importedCount} item{importedCount !== 1 ? "s" : ""} imported.
              {all.some(r => r.status === "skipped_existing") && " Some MCP servers were skipped (already exist)."}
            </p>
          </div>
        </div>

        <div className="border border-zinc-800 divide-y divide-zinc-800">
          {groups.map(({ key, label, icon: Icon }) => {
            const items: ImportResult[] = results[key] || [];
            if (!items.length) return null;
            return (
              <div key={key}>
                <div className="flex items-center gap-2 px-4 py-2.5 bg-zinc-900">
                  <Icon className="h-3.5 w-3.5 text-zinc-500" />
                  <span className="text-[10px] uppercase font-bold tracking-wider text-zinc-500">{label}</span>
                </div>
                {items.map((item, i) => {
                  const StatusIcon = item.status === "imported" ? CheckCircle2 : item.status === "skipped_existing" ? SkipForward : XCircle;
                  const statusCls = item.status === "imported" ? "text-green-400" : item.status === "skipped_existing" ? "text-yellow-400" : "text-red-400";
                  const statusLabel = item.status === "imported" ? "Imported" : item.status === "skipped_existing" ? "Skipped — already exists" : "Error";
                  return (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-t border-zinc-800/60">
                      <StatusIcon className={`h-4 w-4 ${statusCls} flex-shrink-0`} />
                      <span className="flex-1 text-sm text-zinc-200 font-bold">{item.name || item.label}</span>
                      <span className={`text-xs font-mono ${statusCls}`}>{statusLabel}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {results.mcp_servers?.some(m => m.status === "imported") && (
          <div className="flex items-start gap-3 p-4 border border-zinc-800 bg-zinc-900/40">
            <AlertCircle className="h-4 w-4 text-zinc-500 flex-shrink-0 mt-0.5" />
            <p className="text-zinc-500 text-xs leading-relaxed">
              Imported MCP servers have been saved with status <span className="text-zinc-300 font-bold">Disconnected</span>.
              Go to the <span className="text-zinc-300 font-bold">MCP Servers</span> tab and click <span className="text-zinc-300 font-bold">Retry</span> to connect them.
            </p>
          </div>
        )}

        <div className="flex justify-end">
          <button onClick={reset} className="flex items-center gap-2 px-4 py-2 text-sm font-bold border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white transition-colors">
            <Upload className="h-4 w-4" /> Import Another File
          </button>
        </div>
      </div>
    );
  }

  return null;
}
