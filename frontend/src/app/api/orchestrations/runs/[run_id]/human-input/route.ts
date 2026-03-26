import { NextResponse } from 'next/server';
import * as http from 'http';
import { Readable } from 'stream';

const BACKEND_HOST = process.env.BACKEND_HOST || '127.0.0.1';
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT || '8000', 10);

export const maxDuration = 600;
export const dynamic = 'force-dynamic';

export async function POST(
    req: Request,
    { params }: { params: Promise<{ run_id: string }> }
) {
    const { run_id } = await params;
    const body = await req.json();
    const postData = JSON.stringify(body);

    const webStream = await new Promise<ReadableStream>((resolve, reject) => {
        const options: http.RequestOptions = {
            hostname: BACKEND_HOST,
            port: BACKEND_PORT,
            path: `/api/orchestrations/runs/${run_id}/human-input`,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData),
                'Accept-Encoding': 'identity',
            },
        };

        const proxyReq = http.request(options, (proxyRes) => {
            resolve(Readable.toWeb(proxyRes) as ReadableStream);
        });

        proxyReq.on('error', reject);
        proxyReq.write(postData);
        proxyReq.end();
    });

    return new NextResponse(webStream, {
        headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    });
}
