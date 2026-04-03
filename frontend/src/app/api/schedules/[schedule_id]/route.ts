import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export const dynamic = 'force-dynamic';

export async function GET(
    _req: Request,
    { params }: { params: Promise<{ schedule_id: string }> }
) {
    const { schedule_id } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/schedules/${schedule_id}`, { cache: 'no-store' });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        return NextResponse.json({ error: message }, { status: 500 });
    }
}

export async function PUT(
    req: Request,
    { params }: { params: Promise<{ schedule_id: string }> }
) {
    const { schedule_id } = await params;
    try {
        const body = await req.json();
        const res = await fetch(`${BACKEND_URL}/api/schedules/${schedule_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            cache: 'no-store',
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        return NextResponse.json({ error: message }, { status: 500 });
    }
}

export async function PATCH(
    req: Request,
    { params }: { params: Promise<{ schedule_id: string }> }
) {
    const { schedule_id } = await params;
    try {
        const body = await req.json();
        const res = await fetch(`${BACKEND_URL}/api/schedules/${schedule_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            cache: 'no-store',
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        return NextResponse.json({ error: message }, { status: 500 });
    }
}

export async function DELETE(
    _req: Request,
    { params }: { params: Promise<{ schedule_id: string }> }
) {
    const { schedule_id } = await params;
    try {
        const res = await fetch(`${BACKEND_URL}/api/schedules/${schedule_id}`, {
            method: 'DELETE',
            cache: 'no-store',
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        return NextResponse.json({ error: message }, { status: 500 });
    }
}
