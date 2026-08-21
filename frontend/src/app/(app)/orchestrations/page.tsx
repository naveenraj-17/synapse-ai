import { OrchestrationTab } from '@/components/settings/OrchestrationTab';
import { Screen } from '@/components/app/Screen';
import { navEntryFor } from '@/lib/nav';

export const dynamic = 'force-dynamic';

export default async function OrchestrationsPage(props: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
    // Read `?run=` on the server and pass it down. useSearchParams() would force
    // this route's Suspense boundary client-side and ship an empty initial HTML
    // shell — which is exactly what happened to /login.
    const searchParams = await props.searchParams;
    const runId = typeof searchParams.run === 'string' ? searchParams.run : undefined;

    return (
        <Screen nav={navEntryFor('orchestrations')!} bleed>
            <OrchestrationTab initialRunId={runId} />
        </Screen>
    );
}
