import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export async function GET() {
    try {
        const res = await fetch(`${BACKEND_URL}/api/agent-types`);
        if (!res.ok) {
            return NextResponse.json({ types: [] }, { status: res.status });
        }
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error('agent-types proxy error:', message);
        return NextResponse.json({ types: [] }, { status: 500 });
    }
}
