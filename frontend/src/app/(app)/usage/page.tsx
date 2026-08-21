import { UsageTab } from '@/components/settings/UsageTab';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export default function UsagePage() {
    // UsageTab scrolls itself and keeps a sticky action row, so it takes the
    // flex column rather than an outer scroll container.
    return (
        <Screen nav={navEntryFor('usage')!} bleed>
            <UsageTab />
        </Screen>
    );
}
