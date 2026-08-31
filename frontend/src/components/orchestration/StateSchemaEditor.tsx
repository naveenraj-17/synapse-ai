'use client';
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button, Input, Select, Textarea } from '@/components/ui';
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
                    <Input
                        size="sm"
                        type="number"
                        className="font-code"
                        aria-label={`Default for ${key}`}
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
                    <Select
                        size="sm"
                        aria-label={`Default for ${key}`}
                        value={entry.default === true ? 'true' : 'false'}
                        onChange={(v) => updateEntry(key, { default: v === 'true' })}
                        options={[
                            { value: 'false', label: 'false' },
                            { value: 'true', label: 'true' },
                        ]}
                    />
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
                    <div>
                        <Textarea
                            size="sm"
                            className="min-h-[48px] font-code"
                            aria-label={`Default for ${key}`}
                            invalid={hasError}
                            value={display}
                            onChange={(e) => handleJsonChange(key, e.target.value)}
                            placeholder={entry.type === 'list' ? '[]' : '{}'}
                            rows={3}
                        />
                        {hasError && (
                            <p role="alert" className="mt-1 text-[10px] text-danger">
                                Invalid JSON — the value is not saved until it parses.
                            </p>
                        )}
                    </div>
                );
            }
            default:
                return (
                    <Input
                        size="sm"
                        className="font-code"
                        aria-label={`Default for ${key}`}
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
                <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">State Schema</span>
                <Button size="sm" variant="ghost" onClick={addEntry}>
                    <Plus size={12} aria-hidden /> Add key
                </Button>
            </div>
            {entries.length === 0 && (
                <div className="text-xs italic text-text-faint">No state keys defined. Steps will still work with implicit state.</div>
            )}
            {entries.map(([key, entry]) => (
                <div key={key} className="flex items-start gap-2 rounded-md border border-border bg-surface-2/40 p-2">
                    <div className="flex-1 space-y-1.5">
                        <div className="flex gap-2">
                            <Input
                                size="sm"
                                className="flex-1 font-code"
                                aria-label="Key name"
                                value={key}
                                onChange={(e) => updateKey(key, e.target.value)}
                                placeholder="key_name"
                            />
                            <Select
                                size="sm"
                                className="w-24 shrink-0"
                                aria-label={`Type for ${key}`}
                                value={entry.type}
                                onChange={(t) => changeType(key, t)}
                                options={TYPES.map((t) => ({ value: t, label: t }))}
                            />
                        </div>
                        <Input
                            size="sm"
                            aria-label={`Description for ${key}`}
                            value={entry.description}
                            onChange={(e) => updateEntry(key, { description: e.target.value })}
                            placeholder="Description…"
                        />
                        <div className="flex items-center gap-2">
                            <span className="w-12 shrink-0 text-[10px] uppercase tracking-wider text-text-faint">Default</span>
                            <div className="min-w-0 flex-1">{renderDefaultInput(key, entry)}</div>
                        </div>
                    </div>
                    <button
                        type="button"
                        aria-label={`Remove ${key}`}
                        onClick={() => removeEntry(key)}
                        className="mt-1 text-text-faint transition-colors hover:text-danger"
                    >
                        <Trash2 size={12} aria-hidden />
                    </button>
                </div>
            ))}
        </div>
    );
}
