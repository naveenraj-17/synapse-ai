import { Terminal } from 'lucide-react';
import { LocalFile } from '@/types';

interface LocalFileListProps {
    files: LocalFile[];
    onSummarizeFile: (path: string) => void;
    onLocateFile: (path: string) => void;
    onOpenFile: (path: string) => void;
}

export const LocalFileList = ({ files, onSummarizeFile, onLocateFile, onOpenFile }: LocalFileListProps) => {
    if (!files || files.length === 0) return null;

    const isBinary = (path: string) => {
        const ext = path.split('.').pop()?.toLowerCase();
        const binaryExts = ['exe', 'dll', 'zip', 'tar', 'gz', 'iso', 'img', 'bin', 'mp4', 'mp3', 'png', 'jpg', 'jpeg'];
        return binaryExts.includes(ext || '');
    };

    return (
        <div className="mt-4 flex flex-col gap-2 w-full max-w-2xl font-mono">
            <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 border-b border-zinc-900 pb-1">Local Files // Query Results</h3>
            <div className="grid grid-cols-1 gap-px bg-zinc-800 border border-zinc-800">
                {files.map((file, idx) => (
                    <div
                        key={idx}
                        className="group flex items-center justify-between gap-3 bg-black p-3 hover:bg-zinc-900 transition-all"
                    >
                        <div className="flex items-center gap-3 overflow-hidden">
                            <div className="h-8 w-8 shrink-0 flex items-center justify-center border border-zinc-800 text-zinc-500 group-hover:border-white group-hover:text-white transition-colors">
                                <Terminal className="h-4 w-4" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <span className="block text-xs font-bold text-zinc-300 truncate group-hover:text-white transition-colors">{file.name}</span>
                                <span className="text-[10px] text-zinc-600 truncate block font-mono" title={file.path}>{file.path}</span>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={() => onLocateFile(file.path)}
                                className="px-2 py-1 text-[10px] uppercase border border-zinc-800 text-zinc-500 hover:border-white hover:text-white transition-colors"
                                title="Locate in Explorer"
                            >
                                Locate
                            </button>
                            <button
                                onClick={() => onOpenFile(file.path)}
                                className="px-2 py-1 text-[10px] uppercase border border-zinc-800 text-zinc-500 hover:border-white hover:text-white transition-colors"
                                title="Open in Default App"
                            >
                                Open
                            </button>
                            {!isBinary(file.path) && (
                                <button
                                    onClick={() => onSummarizeFile(file.path)}
                                    className="px-2 py-1 text-[10px] uppercase bg-white text-black font-bold hover:bg-zinc-200 transition-colors"
                                >
                                    Summarize
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
