import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8765';

export const dynamic = 'force-dynamic';

export async function GET(
    _req: Request,
    { params }: { params: Promise<{ type: string }> }
) {
    const { type } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/logs/${type}`, { cache: 'no-store' });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
