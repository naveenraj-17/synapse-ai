import { AlertCircle } from 'lucide-react';

interface ConfirmationModalProps {
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    onConfirm: () => void;
    onClose: () => void;
}

export const ConfirmationModal = ({ isOpen, title, message, confirmText = "Yes, Delete It", cancelText = "Cancel", onConfirm, onClose }: ConfirmationModalProps) => {
    if (!isOpen) return null;
    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200 font-mono">
            <div className="w-full max-w-sm border border-red-500/30 bg-black shadow-[0_0_50px_rgba(255,0,0,0.1)] p-6 relative overflow-hidden">
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-transparent via-red-500 to-transparent opacity-50"></div>
                <h3 className="text-lg font-bold text-red-500 mb-4 flex items-center gap-2">
                    <AlertCircle className="h-5 w-5" /> {title.toUpperCase()}
                </h3>
                <p className="text-sm text-zinc-300 mb-8 leading-relaxed whitespace-pre-wrap">
                    {message}
                </p>
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-xs font-medium border border-zinc-800 hover:bg-zinc-900 text-zinc-400 hover:text-white transition-colors"
                    >
                        {cancelText}
                    </button>
                    <button
                        onClick={() => {
                            onConfirm();
                            onClose();
                        }}
                        className="px-4 py-2 text-xs bg-red-900/20 border border-red-900/50 text-red-500 hover:bg-red-900/40 hover:text-red-400 font-bold transition-colors"
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
};
