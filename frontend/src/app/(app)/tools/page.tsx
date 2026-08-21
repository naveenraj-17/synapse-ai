import { SettingsView } from '@/components/SettingsView';

export const dynamic = 'force-dynamic';

/*
 * Tools still reads its state from SettingsView — AgentsTab takes 13 props,
 * CustomToolsTab 17, McpServersTab 12, all drilled from one 1,182-line
 * component. Splitting that is pass two. The URL is already final, so that
 * change swaps this body and nothing else.
 */
export default function ToolsPage() {
    return <SettingsView initialTab="custom_tools" />;
}
