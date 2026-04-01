import { SettingsView } from '@/components/SettingsView';

export const dynamic = 'force-dynamic';

export default async function SettingsPage(props: { params: Promise<{ tab: string }> }) {
    const params = await props.params;
    const tab = params.tab;
    return <SettingsView initialTab={tab} />;
}
