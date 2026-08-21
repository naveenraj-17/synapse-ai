import { LogsTab } from '@/components/settings/LogsTab';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export default function RunsPage() {
    return (
        <Screen nav={navEntryFor('logs')!} bleed>
            <LogsTab />
        </Screen>
    );
}
