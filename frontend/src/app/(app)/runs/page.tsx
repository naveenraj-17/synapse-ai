import { LogsTab } from '@/components/settings/LogsTab';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export default function RunsPage() {
    const nav = navEntryFor('logs')!;

    return (
        <Screen title={nav.label} description={nav.blurb} bleed>
            <LogsTab />
        </Screen>
    );
}
