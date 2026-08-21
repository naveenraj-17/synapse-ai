import { VaultTab } from '@/components/settings/VaultTab';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export default function VaultPage() {
    return (
        <Screen nav={navEntryFor('vault')!} bleed>
            <VaultTab />
        </Screen>
    );
}
