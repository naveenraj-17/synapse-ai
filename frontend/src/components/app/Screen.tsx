/*
 * One page frame for every screen in the app.
 *
 * Before this, four of the work tabs rendered their own <h1> with hand-written
 * copy and the rest got "Manage your agent's {activeTab} configuration." from a
 * template. Title and blurb both come from the nav entry now, so there is
 * exactly one header implementation and exactly one place to edit the words.
 *
 * The header itself is the design system's `PageHeader`, so a screen here and a
 * screen in the cloud product are the same object.
 *
 * No "use client" — it renders no hooks, so it works from a server page and
 * from inside SettingsView alike.
 */
import { X } from 'lucide-react';

import { LinkButton, PageHeader } from '@/components/ui';
import type { NavEntry } from '@/lib/nav';

export function Screen({
    nav,
    bleed = false,
    closeHref,
    children,
}: {
    nav: NavEntry;
    /**
     * For screens that manage their own height — the DAG canvas, the log
     * viewer, the vault file explorer. Gives them a flex column to fill
     * instead of a scroll container to overflow.
     */
    bleed?: boolean;
    /** Renders a close control that leaves the section for this href. */
    closeHref?: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex h-full min-h-0 flex-col">
            <header className="shrink-0 border-b border-border px-6 py-4">
                <PageHeader
                    title={nav.label}
                    description={nav.blurb}
                    actions={closeHref ? (
                        <LinkButton
                            href={closeHref}
                            variant="ghost"
                            iconOnly
                            aria-label="Close settings"
                            title="Close settings"
                        >
                            <X className="size-4" aria-hidden />
                        </LinkButton>
                    ) : undefined}
                />
            </header>

            {bleed ? (
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
            ) : (
                <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-12">
                    <div className="mx-auto max-w-5xl space-y-10">{children}</div>
                </div>
            )}
        </div>
    );
}
