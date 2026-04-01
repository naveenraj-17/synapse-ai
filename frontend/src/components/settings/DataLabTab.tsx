/* eslint-disable @typescript-eslint/no-explicit-any */
import { Database } from 'lucide-react';

interface DataLabTabProps {
    dlTopic: string; setDlTopic: (v: string) => void;
    dlCount: number; setDlCount: (v: number) => void;
    dlProvider: string; setDlProvider: (v: string) => void;
    dlSystemPrompt: string; setDlSystemPrompt: (v: string) => void;
    dlEdgeCases: string; setDlEdgeCases: (v: string) => void;
    dlStatus: any;
    dlDatasets: any[];
    onGenerate: () => void;
}

export const DataLabTab = ({
    dlTopic, setDlTopic, dlCount, setDlCount,
    dlProvider, setDlProvider, dlSystemPrompt, setDlSystemPrompt,
    dlEdgeCases, setDlEdgeCases, dlStatus, dlDatasets, onGenerate
}: DataLabTabProps) => (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 h-full">
        <div className="space-y-6 overflow-y-auto pr-2">
            <div className="space-y-4">
                <div className="space-y-1">
                    <label className="text-[10px] uppercase font-bold text-zinc-500">Domain / Topic</label>
                    <input type="text" value={dlTopic} onChange={e => setDlTopic(e.target.value)}
                        className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none"
                        placeholder="e.g. Medical Assistant, Python Coding Tutor" />
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Count</label>
                        <input type="number" value={dlCount} onChange={e => setDlCount(parseInt(e.target.value))}
                            className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none"
                            min={1} max={100} />
                    </div>
                    <div className="space-y-1">
                        <label className="text-[10px] uppercase font-bold text-zinc-500">Provider</label>
                        <select value={dlProvider} onChange={e => setDlProvider(e.target.value)}
                            className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none appearance-none">
                            <option value="openai">OpenAI (GPT-4o)</option>
                            <option value="gemini">Gemini (1.5 Pro)</option>
                        </select>
                    </div>
                </div>

                <div className="space-y-1">
                    <label className="text-[10px] uppercase font-bold text-zinc-500">Target Persona (System Prompt)</label>
                    <textarea value={dlSystemPrompt} onChange={e => setDlSystemPrompt(e.target.value)}
                        className="w-full h-24 bg-zinc-900 border border-zinc-800 p-3 text-xs font-mono text-zinc-300 focus:border-white focus:outline-none resize-none" />
                </div>

                <div className="space-y-1">
                    <label className="text-[10px] uppercase font-bold text-zinc-500">Edge Cases & Constraints</label>
                    <textarea value={dlEdgeCases} onChange={e => setDlEdgeCases(e.target.value)}
                        className="w-full h-24 bg-zinc-900 border border-zinc-800 p-3 text-xs font-mono text-zinc-300 focus:border-white focus:outline-none resize-none"
                        placeholder="e.g. 'If user asks for illegal advice, politely refuse.' or 'Always include code comments.'" />
                </div>

                <button onClick={onGenerate} disabled={dlStatus?.status === 'generating'}
                    className="w-full py-4 bg-white text-black font-bold text-sm tracking-uppercase hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed">
                    {dlStatus?.status === 'generating' ? 'GENERATING...' : 'START GENERATION JOB'}
                </button>
            </div>
        </div>

        <div className="bg-zinc-950 border border-zinc-800 p-6 flex flex-col h-full">
            <h3 className="text-sm font-bold text-zinc-400 mb-4 flex items-center justify-between">
                <span>DATASETS</span>
                {dlStatus?.status === 'generating' && (
                    <span className="text-green-500 text-xs animate-pulse">Running: {dlStatus.completed}/{dlStatus.total}</span>
                )}
                {dlStatus?.status === 'failed' && (
                    <span className="text-red-500 text-xs">Failed: {dlStatus.error}</span>
                )}
            </h3>

            <div className="flex-1 overflow-y-auto space-y-2">
                {dlDatasets.length === 0 ? (
                    <div className="text-center py-10 text-zinc-600 text-xs italic">No datasets generated yet.</div>
                ) : (
                    dlDatasets.map((ds: any) => (
                        <div key={ds.filename} className="p-3 bg-black border border-zinc-800 flex justify-between items-center group hover:border-zinc-600">
                            <div className="flex-1 min-w-0">
                                <div className="text-xs text-white font-mono truncate mb-1">{ds.filename}</div>
                                <div className="text-[10px] text-zinc-500 flex gap-2">
                                    <span>{(ds.size / 1024).toFixed(1)} KB</span>
                                    <span>•</span>
                                    <span>{new Date(ds.created).toLocaleDateString()}</span>
                                </div>
                            </div>
                            <Database className="h-4 w-4 text-zinc-600 group-hover:text-zinc-400" />
                        </div>
                    ))
                )}
            </div>
        </div>
    </div>
);
