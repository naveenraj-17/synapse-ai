import { SettingsView } from '@/components/SettingsView';

export const dynamic = 'force-dynamic';

export default async function SettingsPage(props: {
    params: Promise<{ tab: string }>;
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
    const params = await props.params;
    const searchParams = await props.searchParams;
    const tab = params.tab;
    const subTab = typeof searchParams.tab === 'string' ? searchParams.tab : undefined;
    return <SettingsView initialTab={tab} initialSubTab={subTab} />;
}
