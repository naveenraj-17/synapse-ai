/*
 * Old /settings/<tab> URLs whose screens moved out to the rail.
 *
 * Deliberately dependency-free: next.config.ts imports this to turn them into
 * real 308s at the routing layer, and it must not drag React or lucide-react
 * into the config load. nav.ts re-exports it so there is still one list.
 *
 * Why the routing layer and not `redirect()` in the page: the app shell is a
 * client layout, so its HTML starts streaming before the page component runs.
 * A redirect thrown at that point arrives in the RSC flight payload instead of
 * as an HTTP status — the browser does follow it, but the response is a 200
 * and the user sees the shell flash first.
 */
export const MOVED_TABS: Record<string, string> = {
    orchestrations: '/orchestrations',
    agents: '/agents',
    custom_tools: '/tools',
    mcp_servers: '/mcp-servers',
    schedules: '/schedules',
    vault: '/vault',
    logs: '/runs',
    usage: '/usage',
};
