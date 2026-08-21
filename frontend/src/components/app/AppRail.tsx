"use client";
/*
 * The persistent left rail. Nine work destinations grouped Build/Operate, with
 * Settings at the foot — replacing twenty flat tabs behind a `fixed inset-0`
 * modal that was blurring a page which wasn't there.
 *
 * Every entry comes from PRIMARY_NAV. There is no second copy of this list.
 *
 * Collapses to icons, by choice (persisted) or because the viewport is narrow.
 * Under `md` it is always collapsed — a 240px rail on a phone leaves nothing
 * for the page.
 */
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Moon, PanelLeftClose, PanelLeftOpen, Settings, Sun } from 'lucide-react';

import { IconButton } from '@/components/ui';
import { PRIMARY_NAV, type NavEntry } from '@/lib/nav';
import { useNotifications } from '@/components/notifications/NotificationProvider';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { useNavGuard } from './NavGuard';
import { usePersisted } from './usePersisted';
import { cn } from '@/lib/utils';

const SETTINGS_HREF = '/settings/general';

function isActive(pathname: string, href: string): boolean {
    if (href === '/') return pathname === '/';
    return pathname === href || pathname.startsWith(`${href}/`);
}

function RailLink({
    href, label, icon: Icon, active, badge, collapsed, onNavigate,
}: {
    href: string;
    label: string;
    icon: NavEntry['icon'];
    active: boolean;
    badge?: number;
    collapsed: boolean;
    onNavigate: (e: React.MouseEvent, href: string) => void;
}) {
    return (
        <Link
            href={href}
            onClick={e => onNavigate(e, href)}
            aria-current={active ? 'page' : undefined}
            title={label}
            className={cn(
                'relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors',
                collapsed ? 'justify-center' : 'justify-center md:justify-start',
                active
                    ? 'bg-surface-2 text-text'
                    : 'text-text-muted hover:bg-surface hover:text-text',
            )}
        >
            {active && (
                <span
                    aria-hidden
                    className={cn(
                        'absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent',
                        collapsed ? 'hidden' : 'hidden md:block',
                    )}
                />
            )}
            <Icon className="h-4 w-4 shrink-0" />
            <span className={cn('truncate', collapsed ? 'hidden' : 'hidden md:inline')}>
                {label}
            </span>
            {badge ? (
                <span className={cn(
                    'flex h-4 min-w-[16px] items-center justify-center rounded-full',
                    'bg-red-500 px-1 text-2xs font-semibold text-white',
                    collapsed
                        ? 'absolute right-1 top-0.5'
                        : 'absolute right-1 top-0.5 md:static md:ml-auto',
                )}>
                    {badge > 9 ? '9+' : badge}
                </span>
            ) : null}
        </Link>
    );
}

export function AppRail({
    theme, onToggleTheme,
}: {
    theme: 'dark' | 'light';
    onToggleTheme: () => void;
}) {
    const pathname = usePathname();
    const router = useRouter();
    const { unseenCount } = useNotifications();
    const mayLeave = useNavGuard();
    const [collapsedFlag, setCollapsed] = usePersisted<'0' | '1'>(
        'synapseRailCollapsed', raw => (raw === '1' ? '1' : '0'), '0');
    const collapsed = collapsedFlag === '1';

    // Chat registers a guard while a run is streaming; honour it before moving.
    const onNavigate = (e: React.MouseEvent, href: string) => {
        e.preventDefault();
        if (isActive(pathname, href)) return;   // already here; don't re-render
        if (!mayLeave()) return;
        router.push(href);
    };

    return (
        <nav
            aria-label="Primary"
            className={cn(
                'flex shrink-0 flex-col border-r border-border bg-bg transition-[width] duration-150',
                collapsed ? 'w-14' : 'w-14 md:w-60',
            )}
        >
            <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-4">
                <span aria-hidden className="size-2 shrink-0 rounded-full bg-accent" />
                <span className={cn(
                    'text-sm font-semibold tracking-tight text-text',
                    collapsed ? 'hidden' : 'hidden md:inline',
                )}>
                    Synapse
                </span>
                {/* Collapse lives at the top while the rail is open, where it
                    is next to the thing it collapses. Collapsed there is no
                    room beside the mark, so the foot control takes over. */}
                {!collapsed && (
                    <IconButton
                        label="Collapse sidebar"
                        title="Collapse sidebar"
                        icon={PanelLeftClose}
                        aria-expanded
                        onClick={() => setCollapsed('1')}
                        className="-mr-2 ml-auto hidden md:inline-flex"
                    />
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-2">
                {PRIMARY_NAV.map(({ group, items }, groupIndex) => (
                    <div key={group ?? 'root'} className="mb-4 last:mb-0">
                        {group && (
                            <div className={cn(
                                'px-2.5 pb-1.5 pt-1 text-2xs font-medium uppercase tracking-wider text-text-faint',
                                collapsed ? 'hidden' : 'hidden md:block',
                            )}>
                                {group}
                            </div>
                        )}
                        {/* Collapsed, the labels are hidden, so a rule is what
                            keeps the groups from reading as one long list.
                            Indexed rather than :first-child — the hidden label
                            is still the first child, so first: would never fire. */}
                        {groupIndex > 0 && (
                            <div className={cn(
                                'mx-2 mb-2 border-t border-border',
                                collapsed ? 'block' : 'block md:hidden',
                            )} />
                        )}
                        <div className="space-y-0.5">
                            {items.map(item => (
                                <RailLink
                                    key={item.href}
                                    href={item.href}
                                    label={item.label}
                                    icon={item.icon}
                                    active={isActive(pathname, item.href)}
                                    badge={item.badge === 'unseenRuns' ? unseenCount : undefined}
                                    collapsed={collapsed}
                                    onNavigate={onNavigate}
                                />
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <div className="shrink-0 space-y-1 border-t border-border p-2">
                <div className={cn(
                    'flex items-center gap-1',
                    collapsed ? 'flex-col' : 'flex-col md:flex-row md:justify-start',
                )}>
                    <NotificationBell placement="above-left" />
                    <button
                        onClick={onToggleTheme}
                        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                        className="rounded-md p-2 text-text-muted transition-colors hover:bg-surface hover:text-text"
                    >
                        {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                    </button>
                    {/* Expand: only while collapsed. Open, the control is in
                        the header — two of them would be noise. */}
                    {collapsed && (
                        <IconButton
                            label="Expand sidebar"
                            title="Expand sidebar"
                            icon={PanelLeftOpen}
                            aria-expanded={false}
                            onClick={() => setCollapsed('0')}
                            className="hidden md:inline-flex"
                        />
                    )}
                </div>
                <RailLink
                    href={SETTINGS_HREF}
                    label="Settings"
                    icon={Settings}
                    active={pathname.startsWith('/settings')}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                />
            </div>
        </nav>
    );
}
