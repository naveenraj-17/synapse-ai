import { UsageTab } from '@/components/settings/UsageTab';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export default function UsagePage() {
    // UsageTab scrolls itself and keeps a sticky action row, so it takes the
    // flex column rather than an outer scroll container.
    const nav = navEntryFor('usage')!;

    return (
        <Screen title={nav.label} description={nav.blurb} bleed>
            <UsageTab />
        </Screen>
    );
}
