import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// Helper to render text with full markdown support
export const renderTextContent = (content: string) => {
    if (!content) return null;

    return (
        <div className="markdown-content">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    // Links open in new tab with external icon
                    a: ({ href, children, ...props }) => (
                        <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 underline underline-offset-2 hover:text-blue-300 break-all inline-flex items-center gap-1"
                            {...props}
                        >
                            {children}
                            <ExternalLink className="inline h-3 w-3 shrink-0" />
                        </a>
                    ),
                    // Tables
                    table: ({ children, ...props }) => (
                        <div className="overflow-x-auto my-3">
                            <table className="w-full border-collapse text-sm" {...props}>
                                {children}
                            </table>
                        </div>
                    ),
                    thead: ({ children, ...props }) => (
                        <thead className="bg-zinc-800/60 text-zinc-300 text-left" {...props}>
                            {children}
                        </thead>
                    ),
                    th: ({ children, ...props }) => (
                        <th className="px-3 py-2 border border-zinc-700 font-semibold text-xs uppercase tracking-wider" {...props}>
                            {children}
                        </th>
                    ),
                    td: ({ children, ...props }) => (
                        <td className="px-3 py-2 border border-zinc-800 text-zinc-200" {...props}>
                            {children}
                        </td>
                    ),
                    tr: ({ children, ...props }) => (
                        <tr className="hover:bg-zinc-800/30 transition-colors" {...props}>
                            {children}
                        </tr>
                    ),
                    // Code blocks
                    code: ({ className, children, ...props }) => {
                        const isInline = !className;
                        if (isInline) {
                            return (
                                <code className="bg-zinc-800 text-emerald-400 px-1.5 py-0.5 rounded text-[13px] font-mono" {...props}>
                                    {children}
                                </code>
                            );
                        }
                        return (
                            <code className={cn("block bg-zinc-900 border border-zinc-800 rounded p-4 overflow-x-auto text-[13px] font-mono text-zinc-200 my-3", className)} {...props}>
                                {children}
                            </code>
                        );
                    },
                    pre: ({ children, ...props }) => (
                        <pre className="bg-zinc-900 border border-zinc-800 rounded p-0 overflow-x-auto my-3" {...props}>
                            {children}
                        </pre>
                    ),
                    // Headings
                    h1: ({ children, ...props }) => (
                        <h1 className="text-xl font-bold text-zinc-100 mt-4 mb-2 pb-1 border-b border-zinc-800" {...props}>{children}</h1>
                    ),
                    h2: ({ children, ...props }) => (
                        <h2 className="text-lg font-bold text-zinc-100 mt-4 mb-2 pb-1 border-b border-zinc-800" {...props}>{children}</h2>
                    ),
                    h3: ({ children, ...props }) => (
                        <h3 className="text-base font-bold text-zinc-200 mt-3 mb-1" {...props}>{children}</h3>
                    ),
                    h4: ({ children, ...props }) => (
                        <h4 className="text-sm font-bold text-zinc-300 mt-2 mb-1" {...props}>{children}</h4>
                    ),
                    // Lists
                    ul: ({ children, ...props }) => (
                        <ul className="list-disc list-inside space-y-1 my-2 ml-2 text-zinc-200" {...props}>{children}</ul>
                    ),
                    ol: ({ children, ...props }) => (
                        <ol className="list-decimal list-inside space-y-1 my-2 ml-2 text-zinc-200" {...props}>{children}</ol>
                    ),
                    li: ({ children, ...props }) => (
                        <li className="text-zinc-200 leading-relaxed" {...props}>{children}</li>
                    ),
                    // Blockquote
                    blockquote: ({ children, ...props }) => (
                        <blockquote className="border-l-2 border-zinc-600 pl-4 my-3 text-zinc-400 italic" {...props}>
                            {children}
                        </blockquote>
                    ),
                    // Horizontal rule
                    hr: (props) => (
                        <hr className="border-zinc-800 my-4" {...props} />
                    ),
                    // Paragraphs
                    p: ({ children, ...props }) => (
                        <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p>
                    ),
                    // Bold
                    strong: ({ children, ...props }) => (
                        <strong className="font-bold text-zinc-50" {...props}>{children}</strong>
                    ),
                    // Emphasis
                    em: ({ children, ...props }) => (
                        <em className="italic text-zinc-300" {...props}>{children}</em>
                    ),
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
};
