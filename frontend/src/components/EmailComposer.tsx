import { useState } from 'react';
import { Send } from 'lucide-react';

interface EmailComposerProps {
    to: string;
    initialSubject: string;
    initialBody: string;
    onSend: (to: string, cc: string, bcc: string, subject: string, body: string) => void;
    onCancel: () => void;
}

export const EmailComposer = ({ to: initialTo, initialSubject, initialBody, onSend, onCancel }: EmailComposerProps) => {
    const [to, setTo] = useState(initialTo);
    const [cc, setCc] = useState('');
    const [bcc, setBcc] = useState('');
    const [subject, setSubject] = useState(initialSubject);
    const [body, setBody] = useState(initialBody);
    const [showCcBcc, setShowCcBcc] = useState(false);

    return (
        <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-4 mt-4 w-full min-w-[600px] max-w-4xl">
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-zinc-400 text-xs uppercase tracking-wider font-semibold">Verify Draft</h3>
                <button
                    onClick={() => setShowCcBcc(!showCcBcc)}
                    className="text-[10px] text-zinc-500 hover:text-white uppercase"
                >
                    {showCcBcc ? '- Hide CC/BCC' : '+ Show CC/BCC'}
                </button>
            </div>

            <div className="space-y-4">
                <div>
                    <label className="block text-zinc-500 text-xs mb-1">To</label>
                    <input
                        type="text"
                        value={to}
                        onChange={(e) => setTo(e.target.value)}
                        className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-white text-sm focus:outline-none focus:border-white transition-colors"
                    />
                </div>

                {showCcBcc && (
                    <div className="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                        <div>
                            <label className="block text-zinc-500 text-xs mb-1">CC</label>
                            <input
                                type="text"
                                value={cc}
                                onChange={(e) => setCc(e.target.value)}
                                placeholder="comma separated"
                                className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-white text-sm focus:outline-none focus:border-white transition-colors"
                            />
                        </div>
                        <div>
                            <label className="block text-zinc-500 text-xs mb-1">BCC</label>
                            <input
                                type="text"
                                value={bcc}
                                onChange={(e) => setBcc(e.target.value)}
                                placeholder="comma separated"
                                className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-white text-sm focus:outline-none focus:border-white transition-colors"
                            />
                        </div>
                    </div>
                )}

                <div>
                    <label className="block text-zinc-500 text-xs mb-1">Subject</label>
                    <input
                        type="text"
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-white text-sm focus:outline-none focus:border-white transition-colors"
                    />
                </div>

                <div>
                    <label className="block text-zinc-500 text-xs mb-1">Body</label>
                    <textarea
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        rows={10}
                        className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-white text-sm font-mono focus:outline-none focus:border-white transition-colors resize-y"
                    />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                    <button
                        onClick={onCancel}
                        className="px-4 py-2 text-zinc-400 hover:text-white text-xs transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => onSend(to, cc, bcc, subject, body)}
                        className="px-4 py-2 bg-white text-black text-xs font-medium rounded hover:bg-zinc-200 transition-colors flex items-center gap-2"
                    >
                        <Send className="h-3 w-3" />
                        Send Email
                    </button>
                </div>
            </div>
        </div>
    );
};
