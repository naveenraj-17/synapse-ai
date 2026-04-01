import { CheckCircle, AlertCircle, XCircle } from 'lucide-react';

type ToastType = 'success' | 'warning' | 'error';

interface ToastProps {
    show: boolean;
    message: string;
    type?: ToastType;
}

const toastStyles: Record<ToastType, string> = {
    success: 'bg-green-500/10 border border-green-500/30 text-green-400',
    warning: 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-300',
    error:   'bg-red-500/10   border border-red-500/30   text-red-400',
};

const ToastIcon: Record<ToastType, React.ElementType> = {
    success: CheckCircle,
    warning: AlertCircle,
    error:   XCircle,
};

export const ToastNotification = ({ show, message, type = 'success' }: ToastProps) => {
    if (!show) return null;
    const Icon = ToastIcon[type];
    return (
        <div className={`fixed top-6 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-2.5 px-4 py-2.5 rounded shadow-2xl text-xs font-medium animate-in fade-in slide-in-from-top-4 duration-300 ${toastStyles[type]}`}>
            <Icon className="h-4 w-4 shrink-0" />
            <span>{message}</span>
        </div>
    );
};
