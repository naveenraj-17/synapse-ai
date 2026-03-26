import { FileText } from 'lucide-react';
import { DriveFile } from '@/types';

interface DriveListProps {
    files: DriveFile[];
}

export const DriveList = ({ files }: DriveListProps) => {
    if (!files || files.length === 0) return null;
    return (
        <div className="mt-4 flex flex-col gap-2 w-full max-w-2xl font-mono">
            <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 border-b border-zinc-900 pb-1">Filesystem // Drive</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-zinc-800 border border-zinc-800">
                {files.map((file) => (
                    <a
                        key={file.id}
                        href={file.webViewLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-center gap-3 bg-black p-3 hover:bg-zinc-900 transition-colors"
                    >
                        <div className="h-8 w-8 flex items-center justify-center border border-zinc-800 text-zinc-500 group-hover:border-white group-hover:text-white transition-colors">
                            <FileText className="h-4 w-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <span className="block text-xs font-bold text-zinc-300 truncate group-hover:text-white transition-colors">{file.name}</span>
                            <span className="text-[10px] text-zinc-600 uppercase">Remote Drive</span>
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
};
