"use client";
/*
 * The persistent left rail. Nine work destinations grouped Build/Operate, with
 * Settings at the foot — replacing twenty flat tabs behind a `fixed inset-0`
 * modal that was blurring a page which wasn't there.
 *
 * Every entry comes from PRIMARY_NAV. There is no second copy of this list.
 *
 * Collapses to icons under `md` so navigation still exists on a phone, which
 * the old horizontally-scrolling tab strip was doing the hard way.
 */
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Moon, Settings, Sun } from 'lucide-react';

import { PRIMARY_NAV, type NavEntry } from '@/lib/nav';
import { useNotifications } from '@/components/notifications/NotificationProvider';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { useNavGuard } from './NavGuard';
import { cn } from '@/lib/utils';

const SETTINGS_HREF = '/settings/general';

function isActive(pathname: string, href: string): boolean {
    if (href === '/') return pathname === '/';
    return pathname === href || pathname.startsWith(`${href}/`);
}

function RailLink({
    href, label, icon: Icon, active, badge, onNavigate,
}: {
    href: string;
    label: string;
    icon: NavEntry['icon'];
    active: boolean;
    badge?: number;
    onNavigate: (e: React.MouseEvent, href: string) => void;
}) {
    return (
        <Link
            href={href}
            onClick={e => onNavigate(e, href)}
            aria-current={active ? 'page' : undefined}
            title={label}
            className={cn(
                'relative flex h-8 items-center gap-2.5 rounded-ui px-2.5 text-ui transition-colors',
                'justify-center md:justify-start',
                active
                    ? 'bg-surface-2 text-content-primary'
                    : 'text-content-secondary hover:bg-surface-1 hover:text-content-primary',
            )}
        >
            {active && (
                <span
                    aria-hidden
                    className="absolute inset-y-1 left-0 hidden w-0.5 rounded-full bg-accent md:block"
                />
            )}
            <Icon className="h-4 w-4 shrink-0" />
            <span className="hidden truncate md:inline">{label}</span>
            {badge ? (
                <span className={cn(
                    'flex h-4 min-w-[16px] items-center justify-center rounded-full',
                    'bg-red-500 px-1 text-2xs font-semibold text-white',
                    'absolute right-1 top-0.5 md:static md:ml-auto',
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
            className="flex w-14 shrink-0 flex-col border-r border-border-subtle bg-surface-0 md:w-60"
        >
            <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border-subtle px-4">
                <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-accent" />
                <span className="hidden text-ui font-semibold tracking-tight text-content-primary md:inline">
                    Synapse
                </span>
            </div>

            <div className="flex-1 overflow-y-auto p-2">
                {PRIMARY_NAV.map(({ group, items }) => (
                    <div key={group ?? 'root'} className="mb-4 last:mb-0">
                        {group && (
                            <div className="hidden px-2.5 pb-1.5 pt-1 text-2xs font-medium uppercase tracking-wider text-content-muted md:block">
                                {group}
                            </div>
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
                                    onNavigate={onNavigate}
                                />
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <div className="shrink-0 space-y-1 border-t border-border-subtle p-2">
                <div className="flex items-center justify-center gap-1 md:justify-start">
                    <NotificationBell placement="above-left" />
                    <button
                        onClick={onToggleTheme}
                        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                        className="rounded-ui p-2 text-content-secondary transition-colors hover:bg-surface-1 hover:text-content-primary"
                    >
                        {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                    </button>
                </div>
                <RailLink
                    href={SETTINGS_HREF}
                    label="Settings"
                    icon={Settings}
                    active={pathname.startsWith('/settings')}
                    onNavigate={onNavigate}
                />
            </div>
        </nav>
    );
}
