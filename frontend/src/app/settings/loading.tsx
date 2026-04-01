"use client";
import { Loader2 } from 'lucide-react';

export default function Loading() {
    return (
        <div className="flex-1 flex flex-col h-full bg-transparent overflow-hidden">
            <div className="flex-1 overflow-y-auto p-6 md:p-12 animate-pulse">
                <div className="max-w-5xl mx-auto space-y-10">
                    <div className="mb-8 space-y-3">
                        <div className="h-10 bg-white/10 w-1/4 rounded"></div>
                        <div className="h-4 bg-white/5 w-1/3 rounded"></div>
                    </div>
                    
                    <div className="space-y-6">
                        <div className="h-6 bg-white/10 w-1/6 rounded"></div>
                        <div className="space-y-3">
                            <div className="h-14 bg-white/5 w-full rounded"></div>
                            <div className="h-14 bg-white/5 w-full rounded"></div>
                            <div className="h-14 bg-white/5 w-full rounded"></div>
                        </div>
                    </div>
                    
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-8 w-8 text-white/20 animate-spin" />
                    </div>
                </div>
            </div>
        </div>
    );
}
