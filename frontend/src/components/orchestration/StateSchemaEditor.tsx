'use client';
import { useState } from 'react';
import { Plus, Trash } from 'lucide-react';
import type { StateSchemaEntry } from '@/types/orchestration';

interface StateSchemaEditorProps {
    schema: Record<string, StateSchemaEntry>;
    onChange: (schema: Record<string, StateSchemaEntry>) => void;
}

const TYPES = ['string', 'number', 'boolean', 'list', 'dict'];

function emptyDefaultFor(type: string): unknown {
    switch (type) {
        case 'number': return 0;
        case 'boolean': return false;
        case 'list': return [];
        case 'dict': return {};
        default: return '';
    }
}

export function StateSchemaEditor({ schema, onChange }: StateSchemaEditorProps) {
    const entries = Object.entries(schema);
    // Raw JSON text buffers for list/dict editors, keyed by entry key.
    // Lets users type freely while we only commit valid JSON to the schema.
    const [jsonBuffers, setJsonBuffers] = useState<Record<string, string>>({});
    const [jsonErrors, setJsonErrors] = useState<Record<string, boolean>>({});

    const addEntry = () => {
        const key = `key_${Date.now()}`;
        onChange({ ...schema, [key]: { type: 'string', default: '', description: '' } });
    };

    const removeEntry = (key: string) => {
        const next = { ...schema };
        delete next[key];
        onChange(next);
        const nextBufs = { ...jsonBuffers }; delete nextBufs[key]; setJsonBuffers(nextBufs);
        const nextErrs = { ...jsonErrors }; delete nextErrs[key]; setJsonErrors(nextErrs);
    };

    const updateKey = (oldKey: string, newKey: string) => {
        if (newKey === oldKey) return;
        const next: Record<string, StateSchemaEntry> = {};
        for (const [k, v] of Object.entries(schema)) {
            next[k === oldKey ? newKey : k] = v;
        }
        onChange(next);
        if (jsonBuffers[oldKey] !== undefined) {
            const nextBufs = { ...jsonBuffers };
            nextBufs[newKey] = nextBufs[oldKey];
            delete nextBufs[oldKey];
            setJsonBuffers(nextBufs);
        }
        if (jsonErrors[oldKey] !== undefined) {
            const nextErrs = { ...jsonErrors };
            nextErrs[newKey] = nextErrs[oldKey];
            delete nextErrs[oldKey];
            setJsonErrors(nextErrs);
        }
    };

    const updateEntry = (key: string, patch: Partial<StateSchemaEntry>) => {
        onChange({ ...schema, [key]: { ...schema[key], ...patch } });
    };

    const changeType = (key: string, newType: string) => {
        // Reset default when type changes to avoid mismatched value/type being saved.
        onChange({ ...schema, [key]: { ...schema[key], type: newType, default: emptyDefaultFor(newType) } });
        const nextBufs = { ...jsonBuffers }; delete nextBufs[key]; setJsonBuffers(nextBufs);
        const nextErrs = { ...jsonErrors }; delete nextErrs[key]; setJsonErrors(nextErrs);
    };

    const handleJsonChange = (key: string, raw: string) => {
        setJsonBuffers({ ...jsonBuffers, [key]: raw });
        try {
            const parsed = raw.trim() === '' ? (schema[key].type === 'list' ? [] : {}) : JSON.parse(raw);
            updateEntry(key, { default: parsed });
            setJsonErrors({ ...jsonErrors, [key]: false });
        } catch {
            setJsonErrors({ ...jsonErrors, [key]: true });
        }
    };

    const renderDefaultInput = (key: string, entry: StateSchemaEntry) => {
        switch (entry.type) {
            case 'number':
                return (
                    <input
                        type="number"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none font-mono"
                        value={entry.default === '' || entry.default == null ? '' : Number(entry.default as number)}
                        onChange={(e) => {
                            const v = e.target.value;
                            updateEntry(key, { default: v === '' ? 0 : Number(v) });
                        }}
                        placeholder="0"
                    />
                );
            case 'boolean':
                return (
                    <select
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none font-mono"
                        value={entry.default === true ? 'true' : 'false'}
                        onChange={(e) => updateEntry(key, { default: e.target.value === 'true' })}
                    >
                        <option value="false">false</option>
                        <option value="true">true</option>
                    </select>
                );
            case 'list':
            case 'dict': {
                const buffered = jsonBuffers[key];
                const display = buffered !== undefined
                    ? buffered
                    : (() => {
                        try { return JSON.stringify(entry.default ?? (entry.type === 'list' ? [] : {}), null, 2); }
                        catch { return entry.type === 'list' ? '[]' : '{}'; }
                    })();
                const hasError = !!jsonErrors[key];
                return (
                    <textarea
                        className={`w-full bg-zinc-900 border rounded-md px-2 py-1 text-xs text-zinc-300 outline-none font-mono resize-y min-h-[48px] ${hasError ? 'border-red-500/60' : 'border-zinc-700'}`}
                        value={display}
                        onChange={(e) => handleJsonChange(key, e.target.value)}
                        placeholder={entry.type === 'list' ? '[]' : '{}'}
                        title={hasError ? 'Invalid JSON — value not saved until parseable' : undefined}
                        rows={3}
                    />
                );
            }
            default:
                return (
                    <input
                        type="text"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none font-mono"
                        value={(entry.default as string) ?? ''}
                        onChange={(e) => updateEntry(key, { default: e.target.value })}
                        placeholder="Default value"
                    />
                );
        }
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
                <div key={key} className="flex items-start gap-2 bg-zinc-800/50 rounded-md p-2">
                    <div className="flex-1 space-y-1">
                        <div className="flex gap-2">
                            <input
                                className="flex-1 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200 font-mono outline-none"
                                value={key}
                                onChange={(e) => updateKey(key, e.target.value)}
                                placeholder="key_name"
                            />
                            <select
                                className="bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200 outline-none"
                                value={entry.type}
                                onChange={(e) => changeType(key, e.target.value)}
                            >
                                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>
                        <input
                            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none"
                            value={entry.description}
                            onChange={(e) => updateEntry(key, { description: e.target.value })}
                            placeholder="Description..."
                        />
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-zinc-500 uppercase tracking-wider w-12 shrink-0">Default</span>
                            <div className="flex-1 min-w-0">{renderDefaultInput(key, entry)}</div>
                        </div>
                    </div>
                    <button onClick={() => removeEntry(key)} className="text-zinc-600 hover:text-red-400 mt-1">
                        <Trash size={12} />
                    </button>
                </div>
            ))}
        </div>
    );
}
