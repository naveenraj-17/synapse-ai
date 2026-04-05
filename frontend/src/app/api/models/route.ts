import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8765';

export async function GET() {
    try {
        const res = await fetch(`${BACKEND_URL}/api/models`);
        if (!res.ok) {
            return NextResponse.json({ providers: {} }, { status: res.status });
        }
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error('models proxy error:', message);
        return NextResponse.json({ providers: {} }, { status: 500 });
    }
}
