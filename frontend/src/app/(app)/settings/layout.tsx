"use client";
/*
 * Settings' own second level, inside the app shell rather than on top of it.
 *
 * The previous version of this file was the modal: `fixed inset-0 z-50
 * bg-black/90 backdrop-blur-md`, a close X that pushed to '/', an Escape
 * handler, and its own copy of the twenty-item tab list. All of that is gone —
 * the rail is the first level, this is the second, and SETTINGS_NAV is the only
 * list.
 *
 * The header band exists so this column and the page header to its right start
 * at the same height and share one continuous rule. Without it the first group
 * label sat flush against the top edge, cramped next to the page title.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';

import { SETTINGS_NAV, visibleItems, type NavFlag } from '@/lib/nav';
import { usePersisted } from '@/components/app/usePersisted';
import { cn } from '@/lib/utils';

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [flags, setFlags] = useState<Partial<Record<NavFlag, boolean>>>({});
    const [collapsedFlag, setCollapsed] = usePersisted<'0' | '1'>(
        'synapseSettingsNavCollapsed', raw => (raw === '1' ? '1' : '0'), '0');
    const collapsed = collapsedFlag === '1';

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
                className={cn(
                    'hidden shrink-0 flex-col border-r border-border-subtle transition-[width] duration-150 lg:flex',
                    collapsed ? 'w-14' : 'w-56',
                )}
            >
                <div className="flex shrink-0 items-start justify-between gap-2 border-b border-border-subtle px-4 py-4">
                    {!collapsed && (
                        <div className="min-w-0">
                            <div className="text-title font-semibold tracking-tight text-content-primary">
                                Settings
                            </div>
                            <p className="mt-1 text-2xs text-content-muted">Workspace configuration.</p>
                        </div>
                    )}
                    <button
                        onClick={() => setCollapsed(collapsed ? '0' : '1')}
                        title={collapsed ? 'Expand settings menu' : 'Collapse settings menu'}
                        aria-expanded={!collapsed}
                        className={cn(
                            'shrink-0 rounded-ui p-2 text-content-secondary transition-colors hover:bg-surface-1 hover:text-content-primary',
                            collapsed ? 'mx-auto' : '-mr-2',
                        )}
                    >
                        {collapsed
                            ? <PanelLeftOpen className="h-4 w-4" />
                            : <PanelLeftClose className="h-4 w-4" />}
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-2">
                    {SETTINGS_NAV.map(({ group, items }) => {
                        const shown = visibleItems(items, flags);
                        if (shown.length === 0) return null;
                        return (
                            <div key={group} className="mb-4 last:mb-0">
                                {collapsed ? (
                                    <div className="mx-2 mb-2 border-t border-border-subtle first:hidden" />
                                ) : (
                                    <div className="px-2.5 pb-1.5 pt-1 text-2xs font-medium uppercase tracking-wider text-content-muted">
                                        {group}
                                    </div>
                                )}
                                <div className="space-y-0.5">
                                    {shown.map(item => {
                                        const active = pathname === item.href;
                                        return (
                                            <Link
                                                key={item.href}
                                                href={item.href}
                                                title={item.label}
                                                aria-current={active ? 'page' : undefined}
                                                className={cn(
                                                    'relative flex h-8 items-center gap-2.5 rounded-ui px-2.5 text-ui transition-colors',
                                                    collapsed && 'justify-center',
                                                    active
                                                        ? 'bg-surface-2 text-content-primary'
                                                        : 'text-content-secondary hover:bg-surface-1 hover:text-content-primary',
                                                )}
                                            >
                                                {active && !collapsed && (
                                                    <span aria-hidden className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent" />
                                                )}
                                                <item.icon className="h-4 w-4 shrink-0" />
                                                {!collapsed && <span className="truncate">{item.label}</span>}
                                            </Link>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>
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
