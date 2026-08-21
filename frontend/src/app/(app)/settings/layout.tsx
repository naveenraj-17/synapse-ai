"use client";
/*
 * Settings' own second level, inside the app shell rather than on top of it.
 *
 * The previous version of this file was the modal: `fixed inset-0 z-50
 * bg-black/90 backdrop-blur-md`, a close X that pushed to '/', an Escape
 * handler, and its own copy of the twenty-item tab list. All of that is gone —
 * the rail is the first level, this is the second, and SETTINGS_NAV is the only
 * list.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

import { SETTINGS_NAV, visibleItems, type NavFlag } from '@/lib/nav';
import { cn } from '@/lib/utils';

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [flags, setFlags] = useState<Partial<Record<NavFlag, boolean>>>({});

    // Messaging, Repos and DB Configs are conditional, exactly as before.
    useEffect(() => {
        fetch('/api/settings')
            .then(r => r.json())
            .then(data => setFlags({
                messaging_enabled: !!data.messaging_enabled,
                coding_agent_enabled: !!data.coding_agent_enabled,
            }))
            .catch(() => { });
    }, []);

    return (
        <div className="flex h-full min-h-0">
            <nav
                aria-label="Settings"
                className="hidden w-56 shrink-0 flex-col overflow-y-auto border-r border-border-subtle p-2 lg:flex"
            >
                {SETTINGS_NAV.map(({ group, items }) => {
                    const shown = visibleItems(items, flags);
                    if (shown.length === 0) return null;
                    return (
                        <div key={group} className="mb-4 last:mb-0">
                            <div className="px-2.5 pb-1.5 pt-1 text-2xs font-medium uppercase tracking-wider text-content-muted">
                                {group}
                            </div>
                            <div className="space-y-0.5">
                                {shown.map(item => {
                                    const active = pathname === item.href;
                                    return (
                                        <Link
                                            key={item.href}
                                            href={item.href}
                                            aria-current={active ? 'page' : undefined}
                                            className={cn(
                                                'flex h-8 items-center gap-2.5 rounded-ui px-2.5 text-ui transition-colors',
                                                active
                                                    ? 'bg-surface-2 text-content-primary'
                                                    : 'text-content-secondary hover:bg-surface-1 hover:text-content-primary',
                                            )}
                                        >
                                            <item.icon className="h-4 w-4 shrink-0" />
                                            <span className="truncate">{item.label}</span>
                                        </Link>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}
            </nav>

            {/* Narrow screens get a horizontal strip instead of the column. */}
            <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-border-subtle p-2 lg:hidden">
                    {SETTINGS_NAV.flatMap(g => visibleItems(g.items, flags)).map(item => {
                        const active = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                aria-current={active ? 'page' : undefined}
                                className={cn(
                                    'flex h-8 shrink-0 items-center gap-2 rounded-ui px-2.5 text-ui transition-colors',
                                    active
                                        ? 'bg-surface-2 text-content-primary'
                                        : 'text-content-secondary hover:bg-surface-1 hover:text-content-primary',
                                )}
                            >
                                <item.icon className="h-4 w-4 shrink-0" />
                                {item.label}
                            </Link>
                        );
                    })}
                </div>
                <div className="min-h-0 flex-1">{children}</div>
            </div>
        </div>
    );
}
