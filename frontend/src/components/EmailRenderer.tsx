import { useState } from 'react';
import { User, Clock } from 'lucide-react';
import { FullEmail } from '@/types';
import { cn } from '@/lib/utils';

interface EmailRendererProps {
    email: FullEmail;
}

export const EmailRenderer = ({ email }: EmailRendererProps) => {
    const [showHtml, setShowHtml] = useState(true);

    if (!email) return null;

    return (
        <div className="mt-4 w-full border border-zinc-800 bg-black font-mono">
            {/* Header */}
            <div className="bg-zinc-950 p-4 border-b border-zinc-800 flex justify-between items-start gap-4">
                <div className="flex-1">
                    <h3 className="text-sm font-bold text-white mb-1 uppercase tracking-wide">{email.subject}</h3>
                    <div className="flex flex-col sm:flex-row sm:items-center gap-4 text-xs text-zinc-500 mt-2">
                        <span className="flex items-center gap-2"><User className="h-3 w-3" /> {email.sender}</span>
                        <span className="flex items-center gap-2"><Clock className="h-3 w-3" /> {email.date}</span>
                    </div>
                </div>
                <div className="flex border border-zinc-800">
                    <button
                        onClick={() => setShowHtml(false)}
                        className={cn("px-3 py-1 text-[10px] uppercase font-bold transition-colors", !showHtml ? "bg-white text-black" : "text-zinc-500 hover:text-white")}
                    >
                        Text
                    </button>
                    <div className="w-px bg-zinc-800"></div>
                    <button
                        onClick={() => setShowHtml(true)}
                        className={cn("px-3 py-1 text-[10px] uppercase font-bold transition-colors", showHtml ? "bg-white text-black" : "text-zinc-500 hover:text-white")}
                    >
                        HTML
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="bg-white h-96 overflow-auto custom-scrollbar relative">
                {showHtml && email.html_body ? (
                    <iframe
                        srcDoc={email.html_body}
                        className="w-full h-full border-none bg-white"
                        sandbox="allow-popups allow-same-origin"
                        title="Email Content"
                    />
                ) : (
                    <pre className="p-4 text-black whitespace-pre-wrap font-mono text-xs">
                        {email.body}
                    </pre>
                )}
            </div>
        </div>
    );
};
