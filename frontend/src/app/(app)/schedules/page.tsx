import { SchedulesTab } from '@/components/settings/SchedulesTab';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export default function SchedulesPage() {
    return (
        <Screen nav={navEntryFor('schedules')!} bleed>
            <SchedulesTab />
        </Screen>
    );
}
