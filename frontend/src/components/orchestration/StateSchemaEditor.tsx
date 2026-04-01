'use client';
import { Plus, Trash } from 'lucide-react';
import type { StateSchemaEntry } from '@/types/orchestration';

interface StateSchemaEditorProps {
    schema: Record<string, StateSchemaEntry>;
    onChange: (schema: Record<string, StateSchemaEntry>) => void;
}

const TYPES = ['string', 'number', 'boolean', 'list', 'dict'];

export function StateSchemaEditor({ schema, onChange }: StateSchemaEditorProps) {
    const entries = Object.entries(schema);

    const addEntry = () => {
        const key = `key_${Date.now()}`;
        onChange({ ...schema, [key]: { type: 'string', default: '', description: '' } });
    };

    const removeEntry = (key: string) => {
        const next = { ...schema };
        delete next[key];
        onChange(next);
    };

    const updateKey = (oldKey: string, newKey: string) => {
        if (newKey === oldKey) return;
        const next: Record<string, StateSchemaEntry> = {};
        for (const [k, v] of Object.entries(schema)) {
            next[k === oldKey ? newKey : k] = v;
        }
        onChange(next);
    };

    const updateEntry = (key: string, patch: Partial<StateSchemaEntry>) => {
        onChange({ ...schema, [key]: { ...schema[key], ...patch } });
    };

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">State Schema</span>
                <button onClick={addEntry} className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                    <Plus size={12} /> Add Key
                </button>
            </div>
            {entries.length === 0 && (
                <div className="text-xs text-zinc-600 italic">No state keys defined. Steps will still work with implicit state.</div>
            )}
            {entries.map(([key, entry]) => (
                <div key={key} className="flex items-start gap-2 bg-zinc-800/50 rounded p-2">
                    <div className="flex-1 space-y-1">
                        <div className="flex gap-2">
                            <input
                                className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 font-mono outline-none"
                                value={key}
                                onChange={(e) => updateKey(key, e.target.value)}
                                placeholder="key_name"
                            />
                            <select
                                className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 outline-none"
                                value={entry.type}
                                onChange={(e) => updateEntry(key, { type: e.target.value })}
                            >
                                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>
                        <input
                            className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none"
                            value={entry.description}
                            onChange={(e) => updateEntry(key, { description: e.target.value })}
                            placeholder="Description..."
                        />
                    </div>
                    <button onClick={() => removeEntry(key)} className="text-zinc-600 hover:text-red-400 mt-1">
                        <Trash size={12} />
                    </button>
                </div>
            ))}
        </div>
    );
}
