export const ToastNotification = ({ show }: { show: boolean }) => {
    if (!show) return null;
    return (
        <div className="fixed top-8 left-1/2 -translate-x-1/2 z-[100] bg-green-500 text-black px-6 py-2 rounded-full shadow-2xl font-bold text-xs uppercase animate-in fade-in slide-in-from-top-4 duration-300 flex items-center gap-2">
            <div className="h-2 w-2 bg-black rounded-full animate-pulse"></div>
            Configuration Saved
        </div>
    );
};
