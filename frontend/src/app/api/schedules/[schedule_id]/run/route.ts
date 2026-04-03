import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export const dynamic = 'force-dynamic';

export async function POST(
    _req: Request,
    { params }: { params: Promise<{ schedule_id: string }> }
) {
    const { schedule_id } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/schedules/${schedule_id}/run`, {
            method: 'POST',
            cache: 'no-store',
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        return NextResponse.json({ error: message }, { status: 500 });
    }
}
