import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8765';

export const maxDuration = 300; // 5 minutes timeout for streaming

export async function POST(req: Request) {
    try {
        const body = await req.json();

        // Forward request to Python Backend SSE endpoint
        const backendResponse = await fetch(`${BACKEND_URL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!backendResponse.ok) {
            const text = await backendResponse.text();
            return NextResponse.json(
                { error: `Backend Error ${backendResponse.status}: ${text}` }, 
                { status: backendResponse.status }
            );
        }

        // Stream the response from backend to frontend
        // This passes through the SSE stream
        return new NextResponse(backendResponse.body, {
            headers: {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            },
        });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
        console.error("SSE Proxy Error:", error);
        return NextResponse.json({ error: `Proxy Error: ${error.message}` }, { status: 500 });
    }
}
