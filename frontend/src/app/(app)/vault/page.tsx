import { VaultTab } from '@/components/settings/VaultTab';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export default function VaultPage() {
    const nav = navEntryFor('vault')!;

    return (
        <Screen title={nav.label} description={nav.blurb} bleed>
            <VaultTab />
        </Screen>
    );
}
