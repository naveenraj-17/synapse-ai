/*
 * One page frame for every screen in the app.
 *
 * Before this, four of the work tabs rendered their own <h1> with hand-written
 * copy and the rest got "Manage your agent's {tab} configuration." from a
 * template. Title and blurb both come from the nav entry now, so there is
 * exactly one header implementation and exactly one place to edit the words.
 *
 * No "use client" — it renders no hooks, so it works from a server page and
 * from inside SettingsView alike.
 */
import type { NavEntry } from '@/lib/nav';

export function Screen({
    nav,
    bleed = false,
    children,
}: {
    nav: NavEntry;
    /**
     * For screens that manage their own height — the DAG canvas, the log
     * viewer, the vault file explorer. Gives them a flex column to fill
     * instead of a scroll container to overflow.
     */
    bleed?: boolean;
    children: React.ReactNode;
}) {
    return (
        <div className="flex h-full min-h-0 flex-col">
            <header className="shrink-0 border-b border-border-subtle px-6 py-4">
                <h1 className="text-title font-semibold tracking-tight text-content-primary">
                    {nav.label}
                </h1>
                <p className="mt-1 text-2xs text-content-muted">{nav.blurb}</p>
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
