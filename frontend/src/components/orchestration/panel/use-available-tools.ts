'use client';

/**
 * The tool catalogue, fetched once per panel mount. Both the tool step's
 * picker and the agent step's allowed-tools narrowing read it; a 404 (or any
 * failure) degrades to an empty list, which hides those affordances rather
 * than breaking the panel — the contract the cloud fork relies on.
 */

import { useEffect, useState } from 'react';

export interface AvailableTool {
    name: string;
    description: string;
}

export function useAvailableTools(): AvailableTool[] {
    const [tools, setTools] = useState<AvailableTool[]>([]);
    useEffect(() => {
        fetch('/api/tools/available')
            .then((r) => (r.ok ? r.json() : { tools: [] }))
            .then((d) => setTools(Array.isArray(d.tools) ? d.tools : []))
            .catch(() => {});
    }, []);
    return tools;
}
