import { Dashboard } from '@/components/app/Dashboard';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export default function DashboardPage() {
    return (
        <Screen nav={navEntryFor('dashboard')!}>
            <Dashboard />
        </Screen>
    );
}
