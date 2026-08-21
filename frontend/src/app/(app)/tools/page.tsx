import { ToolsScreen } from '@/components/settings/ToolsScreen';
import { Screen } from '@/components/ui';
import { navEntryFor } from '@/lib/nav';

export const dynamic = 'force-dynamic';

/*
 * A real page. It used to render <SettingsView initialTab="custom_tools" />, which
 * meant this screen's state was held in a 1,087-line component alongside the
 * Models tab's forty API-key fields and drilled back down as props.
 *
 * The <Screen> shell and the title both come from the nav entry, exactly as
 * they did when SettingsView wrapped this — so the header is unchanged and
 * there is still one place the words live.
 */
export default function ToolsPage() {
    const nav = navEntryFor('custom_tools')!;

    return (
        <Screen title={nav.label} description={nav.blurb}>
            <ToolsScreen />
        </Screen>
    );
}
