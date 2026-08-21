"use client";
/*
 * The application shell: persistent rail, one <main>, a real page.
 *
 * Replaces app/settings/layout.tsx, which rendered `fixed inset-0 z-50
 * bg-black/90 backdrop-blur-md` with a close X — a dialog drawn over a page
 * that was never there, because Settings is a route.
 *
 * Owns the theme for the whole app. Both the chat page and the old settings
 * shell used to read `synapseTheme` separately; now it is read once, and always
 * AFTER hydration — reading localStorage during render mismatches the SSR HTML.
 */
import { useCallback, useSyncExternalStore } from 'react';

import { AppRail } from '@/components/app/AppRail';
import { NavGuardProvider } from '@/components/app/NavGuard';
import { cn } from '@/lib/utils';

const THEME_KEY = 'synapseTheme';
const THEME_EVENT = 'synapse-theme';

function subscribe(onChange: () => void) {
    window.addEventListener(THEME_EVENT, onChange);
    window.addEventListener('storage', onChange);   // and across tabs, for free
    return () => {
        window.removeEventListener(THEME_EVENT, onChange);
        window.removeEventListener('storage', onChange);
    };
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
    // localStorage is an external store, so read it as one. The server snapshot
    // is 'dark', which is what the SSR HTML renders — no mismatch, and no
    // setState inside an effect to trigger a cascading render.
    const theme = useSyncExternalStore(
        subscribe,
        () => (localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'),
        () => 'dark' as const,
    );

    const toggleTheme = useCallback(() => {
        const next = localStorage.getItem(THEME_KEY) === 'light' ? 'dark' : 'light';
        localStorage.setItem(THEME_KEY, next);
        window.dispatchEvent(new Event(THEME_EVENT));
    }, []);

    return (
        <NavGuardProvider>
            <div
                className={cn(
                    'flex h-screen overflow-hidden bg-surface-0 font-ui text-content-primary',
                    theme === 'light' && 'light-mode',
                )}
            >
                <AppRail theme={theme} onToggleTheme={toggleTheme} />
                {/* The only <main> in the app. Pages render a plain flex column
                    inside it — a nested <main> gives two landmarks and two
                    scrollbars. */}
                <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
            </div>
        </NavGuardProvider>
    );
}
