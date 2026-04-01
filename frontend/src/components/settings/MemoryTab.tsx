import React from 'react';
import { Database, MessageSquare, Brain, Trash2, AlertTriangle, Shield } from 'lucide-react';

const CATEGORIES = [
  {
    id: 'conversation',
    label: 'Conversation History',
    icon: MessageSquare,
    description: 'Past messages and chat logs between you and agents.'
  },
  {
    id: 'knowledge',
    label: 'Knowledge Base',
    icon: Brain,
    description: 'Learned information and documents processed by agents.'
  },
  {
    id: 'system',
    label: 'System Logs',
    icon: Shield,
    description: 'Internal execution logs and diagnostic data.'
  }
];

export const MemoryTab = () => {
    const [selected, setSelected] = React.useState<string[]>([]);

    const toggle = (id: string) => {
        setSelected(prev => 
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        );
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-zinc-800/50 pb-4">
                <div>
                    <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                        Data Categories
                    </h3>
                    <p className="text-zinc-500 text-sm mt-1">Select the data pipelines you want to permanently clear.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {CATEGORIES.map((item) => {
                    const Icon = item.icon;
                    const isChecked = selected.includes(item.id);
                    return (
                        <div 
                            key={item.id}
                            onClick={() => toggle(item.id)}
                            className={`flex items-start gap-4 p-4 border transition-all cursor-pointer group ${
                                isChecked 
                                    ? 'bg-red-950/20 border-red-900/50' 
                                    : 'bg-zinc-900/40 border-zinc-800/50 hover:border-zinc-700/50 hover:bg-zinc-900/80'
                            }`}
                        >
                            {/* Custom checkbox */}
                            <div className={`mt-0.5 h-4 w-4 flex-shrink-0 flex items-center justify-center transition-colors border ${isChecked ? 'bg-red-500 border-red-500' : 'bg-zinc-950 border-zinc-700 group-hover:border-zinc-500'}`}>
                                {isChecked && (
                                    <svg className="h-3 w-3 text-black" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                        <polyline points="2,6 5,9 10,3" />
                                    </svg>
                                )}
                            </div>

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <Icon className={`h-4 w-4 flex-shrink-0 transition-colors ${isChecked ? 'text-red-400' : 'text-zinc-500 group-hover:text-zinc-400'}`} />
                                    <div className={`text-sm font-bold tracking-wide transition-colors ${isChecked ? 'text-red-200' : 'text-zinc-200 group-hover:text-zinc-100'}`}>{item.label}</div>
                                </div>
                                <div className={`text-xs transition-colors mt-1.5 leading-relaxed ${isChecked ? 'text-red-400/70':'text-zinc-500 group-hover:text-zinc-400'}`}>{item.description}</div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Danger Zone */}
            <div className="mt-8 pt-6 border-t border-zinc-800/50">
                <div className="bg-transparent border border-red-900/30 p-5 md:p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 md:gap-8 hover:border-red-900/50 transition-colors">
                    <div>
                        <h3 className="text-sm uppercase tracking-wider font-bold text-red-500 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" />
                            Danger Zone
                        </h3>
                        <p className="text-zinc-500 text-sm mt-1">Permanently delete selected data categories. This action cannot be undone.</p>
                    </div>
                    <button 
                        disabled={selected.length === 0}
                        className="px-6 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold transition-all flex items-center justify-center gap-2"
                    >
                        <Trash2 className="h-4 w-4" />
                        Clear Selected Data
                    </button>
                </div>
            </div>
        </div>
    );
};
