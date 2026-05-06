/**
 * Next.js Edge Middleware
 * -----------------------
 * Injects the X-Synapse-Internal header into requests that get rewritten
 * to the backend via next.config.ts fallback rewrites.
 * 
 * This covers routes like /api/settings, /api/agents, /api/tools, etc.
 * that don't have explicit Next.js API route handlers and are proxied
 * directly via the rewrite rules.
 */
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
    const token = process.env.SYNAPSE_INTERNAL_TOKEN || '';
    if (!token) {
        return NextResponse.next();
    }

    // Clone request headers and inject the internal token
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('X-Synapse-Internal', token);

    return NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });
}

export const config = {
    // Run on API and auth routes that may be rewritten to the backend
    matcher: ['/api/:path*', '/auth/:path*'],
};
