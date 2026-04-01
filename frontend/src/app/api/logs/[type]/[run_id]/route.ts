import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export const dynamic = 'force-dynamic';

export async function GET(
    _req: Request,
    { params }: { params: Promise<{ type: string; run_id: string }> }
) {
    const { type, run_id } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/logs/${type}/${run_id}`, { cache: 'no-store' });
        if (!res.ok) return NextResponse.json({ error: 'Not found' }, { status: res.status });
        const text = await res.text();
        return new NextResponse(text, {
            status: 200,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}

export async function DELETE(
    _req: Request,
    { params }: { params: Promise<{ type: string; run_id: string }> }
) {
    const { type, run_id } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/logs/${type}/${run_id}`, {
            method: 'DELETE',
            cache: 'no-store',
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
