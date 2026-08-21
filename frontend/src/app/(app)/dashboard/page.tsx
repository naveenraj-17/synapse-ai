import { Dashboard } from '@/components/app/Dashboard';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export default function DashboardPage() {
    const nav = navEntryFor('dashboard')!;

    return (
        <Screen title={nav.label} description={nav.blurb}>
            <Dashboard />
        </Screen>
    );
}
