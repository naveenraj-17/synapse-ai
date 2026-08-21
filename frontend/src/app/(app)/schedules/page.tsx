import { SchedulesTab } from '@/components/settings/SchedulesTab';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export default function SchedulesPage() {
    const nav = navEntryFor('schedules')!;

    return (
        <Screen title={nav.label} description={nav.blurb} bleed>
            <SchedulesTab />
        </Screen>
    );
}
