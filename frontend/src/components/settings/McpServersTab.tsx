/* eslint-disable @typescript-eslint/no-explicit-any */
import { Server, Plus, Trash } from 'lucide-react';

interface McpServersTabProps {
    mcpServers: any[];
    loadingMcp: boolean;
    draftMcpServer: { name: string; command: string; args: string; env: { key: string; value: string }[] };
    setDraftMcpServer: (v: { name: string; command: string; args: string; env: { key: string; value: string }[] }) => void;
    onAddServer: () => void;
    onDeleteServer: (name: string) => void;
}

export const McpServersTab = ({
    mcpServers, loadingMcp, draftMcpServer, setDraftMcpServer,
    onAddServer, onDeleteServer
}: McpServersTabProps) => (
    <div className="space-y-8">
        <div className="mb-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Server className="h-5 w-5" />
                External MCP Servers
            </h3>
            <p className="text-zinc-500 text-sm mt-1">
                Connect external Model Context Protocol (MCP) servers to extend agent capabilities with local tools, databases, and APIs.
            </p>
        </div>

        {/* Connected Servers List */}
        <div className="space-y-4">
            <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Connected Servers</h4>
            {loadingMcp ? (
                <div className="text-zinc-500 text-sm italic">Loading servers...</div>
            ) : mcpServers.length === 0 ? (
                <div className="p-8 text-center border border-dashed border-zinc-800 rounded bg-zinc-900/30">
                    <Server className="h-8 w-8 mx-auto text-zinc-700 mb-2" />
                    <p className="text-zinc-500 text-sm">No servers connected.</p>
                </div>
            ) : (
                <div className="grid gap-3">
                    {mcpServers.map((server) => (
                        <div key={server.name} className="flex items-center justify-between p-4 bg-zinc-900 border border-zinc-800 rounded group">
                            <div className="flex flex-col gap-1">
                                <div className="flex items-center gap-2">
                                    <span className="font-bold text-white text-sm">{server.name}</span>
                                    <span className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30 uppercase">Active</span>
                                </div>
                                <code className="text-[10px] text-zinc-500 font-mono">
                                    {server.command} {(server.args || []).join(' ')}
                                </code>
                            </div>
                            <button 
                                onClick={() => onDeleteServer(server.name)}
                                className="p-2 text-zinc-600 hover:text-red-500 hover:bg-zinc-800 rounded transition-colors"
                            >
                                <Trash className="h-4 w-4" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>

        {/* Add Server Form */}
        <div className="pt-6 border-t border-zinc-800 space-y-6">
             <h4 className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Add New Server</h4>
             
             <div className="grid grid-cols-2 gap-4">
                 <div className="space-y-2">
                     <label className="text-[10px] uppercase font-bold text-zinc-500">Server Name</label>
                     <input 
                         type="text" 
                         value={draftMcpServer.name}
                         onChange={e => setDraftMcpServer({...draftMcpServer, name: e.target.value})}
                         className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none placeholder:text-zinc-700"
                         placeholder="e.g. filesystem"
                     />
                 </div>
                 <div className="space-y-2">
                     <label className="text-[10px] uppercase font-bold text-zinc-500">Command</label>
                     <input 
                         type="text" 
                         value={draftMcpServer.command}
                         onChange={e => setDraftMcpServer({...draftMcpServer, command: e.target.value})}
                         className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700"
                         placeholder="e.g. npx, uvx, python3"
                     />
                 </div>
                 <div className="col-span-2 space-y-2">
                     <label className="text-[10px] uppercase font-bold text-zinc-500">Arguments</label>
                     <input 
                         type="text" 
                         value={draftMcpServer.args}
                         onChange={e => setDraftMcpServer({...draftMcpServer, args: e.target.value})}
                         className="w-full bg-zinc-900 border border-zinc-800 p-2 text-sm text-white focus:border-white focus:outline-none font-mono placeholder:text-zinc-700"
                         placeholder='-y @modelcontextprotocol/server-filesystem /path/to/allow'
                     />
                     <p className="text-[10px] text-zinc-600">Space separated arguments.</p>
                 </div>
             </div>

             <div className="space-y-2">
                 <div className="flex items-center justify-between">
                     <label className="text-[10px] uppercase font-bold text-zinc-500">Environment Variables</label>
                     <button 
                         onClick={() => setDraftMcpServer({
                             ...draftMcpServer, 
                             env: [...draftMcpServer.env, {key: '', value: ''}]
                         })}
                         className="text-[10px] font-bold text-zinc-400 hover:text-white flex items-center gap-1"
                     >
                         <Plus className="h-3 w-3" /> ADD VAR
                     </button>
                 </div>
                 {draftMcpServer.env.map((env, idx) => (
                     <div key={idx} className="flex gap-2">
                         <input 
                             type="text" 
                             placeholder="KEY" 
                             value={env.key} 
                             onChange={e => {
                                 const newEnv = [...draftMcpServer.env];
                                 newEnv[idx].key = e.target.value;
                                 setDraftMcpServer({...draftMcpServer, env: newEnv});
                             }}
                             className="flex-1 bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none"
                         />
                          <input 
                             type="text" 
                             placeholder="VALUE" 
                             value={env.value} 
                             onChange={e => {
                                 const newEnv = [...draftMcpServer.env];
                                 newEnv[idx].value = e.target.value;
                                 setDraftMcpServer({...draftMcpServer, env: newEnv});
                             }}
                             className="flex-[2] bg-zinc-900 border border-zinc-800 p-2 text-xs text-white font-mono focus:border-white focus:outline-none"
                         />
                         <button 
                            onClick={() => {
                                const newEnv = draftMcpServer.env.filter((_, i) => i !== idx);
                                setDraftMcpServer({...draftMcpServer, env: newEnv});
                            }}
                            className="p-2 text-zinc-600 hover:text-red-500"
                         >
                             <Trash className="h-4 w-4" />
                         </button>
                     </div>
                 ))}
             </div>

             <div className="flex justify-end pt-4">
                 <button 
                     onClick={onAddServer}
                     className="px-6 py-2 bg-white text-black text-sm font-bold hover:bg-zinc-200 transition-colors"
                 >
                     Connect Server
                 </button>
             </div>
        </div>
    </div>
);
