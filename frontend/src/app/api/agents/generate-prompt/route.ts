import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8765';

export const maxDuration = 300; // 5 minutes timeout for LLM prompt generation

export async function POST(req: Request) {
    try {
        const body = await req.json();

        const backendResponse = await fetch(`${BACKEND_URL}/api/agents/generate-prompt`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!backendResponse.ok) {
            const text = await backendResponse.text();
            return NextResponse.json({ error: `Backend Error ${backendResponse.status}: ${text}` }, { status: backendResponse.status });
        }

        const data = await backendResponse.json();
        return NextResponse.json(data);

    } catch (error: any) {
        console.error("Generate prompt proxy error:", error);
        return NextResponse.json({ error: `Proxy Error: ${error.message}` }, { status: 500 });
    }
}
