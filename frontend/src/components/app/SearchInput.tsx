"use client";
/*
 * One search control, so the three lists that needed one look like each other.
 *
 * Deliberately uncontrolled about its own layout: callers give it a width.
 */
import { Search, X } from 'lucide-react';

export function SearchInput({
    value, onChange, placeholder = 'Search…', className = '', autoFocus = false,
}: {
    value: string;
    onChange: (next: string) => void;
    placeholder?: string;
    className?: string;
    autoFocus?: boolean;
}) {
    return (
        <div className={`relative ${className}`}>
            <Search
                aria-hidden
                className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-muted"
            />
            <input
                type="search"
                role="searchbox"
                value={value}
                autoFocus={autoFocus}
                onChange={e => onChange(e.target.value)}
                placeholder={placeholder}
                className="h-8 w-full rounded-ui border border-border-subtle bg-surface-1 pl-8 pr-8 text-ui
                           text-content-primary placeholder:text-content-muted
                           focus:border-border-strong transition-colors
                           [&::-webkit-search-cancel-button]:hidden"
            />
            {value && (
                <button
                    type="button"
                    onClick={() => onChange('')}
                    aria-label="Clear search"
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-ui p-1 text-content-muted transition-colors hover:text-content-primary"
                >
                    <X className="h-3 w-3" />
                </button>
            )}
        </div>
    );
}

/** Case-insensitive "every word appears somewhere in one of these fields". */
export function matchesQuery(query: string, ...fields: (string | undefined | null)[]): boolean {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const hay = fields.filter(Boolean).join(' ').toLowerCase();
    return q.split(/\s+/).every(word => hay.includes(word));
}
