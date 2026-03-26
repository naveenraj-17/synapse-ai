import { Email } from '@/types';

interface EmailListProps {
    emails: Email[];
    onEmailClick: (id: string) => void;
}

export const EmailList = ({ emails, onEmailClick }: EmailListProps) => {
    if (!emails || !Array.isArray(emails) || emails.length === 0) return null;
    return (
        <div className="mt-4 flex flex-col gap-px w-full max-w-2xl border border-zinc-800 bg-zinc-900">
            {emails.map((email) => (
                <div
                    key={email.id}
                    onClick={() => onEmailClick(email.id)}
                    className="group relative flex flex-col gap-1 bg-black p-4 hover:bg-zinc-900 transition-colors cursor-pointer border-b border-zinc-900 last:border-0"
                >
                    <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-sm truncate pr-4 font-mono">{email.sender}</span>
                        <span className="text-[10px] text-zinc-600 font-mono tracking-tighter">{email.id.slice(-8)}</span>
                    </div>
                    <span className="text-xs text-zinc-400 font-mono truncate group-hover:text-white transition-colors">{email.subject}</span>
                </div>
            ))}
        </div>
    );
};
