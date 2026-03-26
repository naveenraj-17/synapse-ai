import { Database, Trash } from 'lucide-react';

interface MemoryTabProps {
    onClearHistory: (type: 'recent' | 'all') => void;
}

export const MemoryTab = ({ onClearHistory }: MemoryTabProps) => (
    <div className="space-y-8">
        <div className="p-6 bg-red-950/10 border border-red-900/30 space-y-6">
            <div>
                <h3 className="text-lg font-bold text-red-500 flex items-center gap-2">
                    <Database className="h-5 w-5" />
                    Danger Zone
                </h3>
                <p className="text-sm text-red-900/70 mt-1">Manage your agents memory and history. Actions here are irreversible.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <button
                    onClick={() => onClearHistory('recent')}
                    className="flex flex-col items-start p-4 bg-red-900/10 border border-red-900/30 hover:bg-red-900/20 hover:border-red-500/50 transition-all text-left"
                >
                    <span className="font-bold text-red-400 mb-1 flex items-center gap-2">
                        <Trash className="h-4 w-4" /> Clear Recent
                    </span>
                    <span className="text-xs text-red-900/60">Removes strictly the current session&apos;s short-term conversation buffer.</span>
                </button>

                <button
                    onClick={() => onClearHistory('all')}
                    className="flex flex-col items-start p-4 bg-red-950/30 border border-red-900/50 hover:bg-red-900/40 hover:border-red-500 transition-all text-left"
                >
                    <span className="font-bold text-red-400 mb-1 flex items-center current-color gap-2">
                        <Trash className="h-4 w-4" /> Clear All History
                    </span>
                    <span className="text-xs text-red-900/60">Detailed wipe of ALL long-term memories (Vector DB) and session data.</span>
                </button>
            </div>
        </div>
    </div>
);
