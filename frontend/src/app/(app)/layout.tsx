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
import { useEffect } from 'react';

import { AppRail } from '@/components/app/AppRail';
import { NavGuardProvider } from '@/components/app/NavGuard';
import { usePersisted } from '@/components/app/usePersisted';

export default function AppLayout({ children }: { children: React.ReactNode }) {
    const [theme, setTheme] = usePersisted<'dark' | 'light'>(
        'synapseTheme', raw => (raw === 'light' ? 'light' : 'dark'), 'dark');

    // The class goes on <html>, not on the shell div. `body` resolves
    // `--background` against itself, so a .light-mode starting below body left
    // the page ground dark behind a light app — visible on overscroll and
    // behind the app-wide toast host, which renders outside this shell.
    // Writing to the DOM is what an effect is actually for.
    useEffect(() => {
        const root = document.documentElement;
        root.classList.toggle('light-mode', theme === 'light');
        return () => root.classList.remove('light-mode');
    }, [theme]);

    return (
        <NavGuardProvider>
            <div className="flex h-screen overflow-hidden bg-surface-0 font-ui text-content-primary">
                <AppRail theme={theme} onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')} />
                {/* The only <main> in the app. Pages render a plain flex column
                    inside it — a nested <main> gives two landmarks and two
                    scrollbars. */}
                <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
            </div>
        </NavGuardProvider>
    );
}
