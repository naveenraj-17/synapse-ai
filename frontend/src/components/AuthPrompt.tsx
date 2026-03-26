import { Shield, Settings, ExternalLink } from 'lucide-react';

interface AuthPromptProps {
    onOpenSettings: () => void;
    credentials?: any;
}

export const AuthPrompt = ({ onOpenSettings, credentials }: AuthPromptProps) => {
    const hasCredentials = !!credentials?.client_id;

    return (
        <div className="mt-4 w-full max-w-md border border-white/20 bg-zinc-950 p-6 shadow-xl">
            <div className="flex flex-col items-center gap-4 text-center">
                <div className="h-12 w-12 border border-white/10 flex items-center justify-center text-white">
                    <Shield className="h-6 w-6" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-white uppercase tracking-wider">
                        {hasCredentials ? "Authentication Required" : "Setup Required"}
                    </h3>
                    <p className="text-xs text-zinc-500 mt-1 font-mono">
                        {hasCredentials
                            ? "Click to authorize access to your Google Workspace."
                            : "Please upload your 'credentials.json' in Settings first."}
                    </p>
                </div>

                {hasCredentials ? (
                    <a
                        href="/auth/login"
                        className="flex items-center gap-2 border border-white px-6 py-3 text-xs font-bold text-white uppercase hover:bg-white hover:text-black transition-all"
                    >
                        <ExternalLink className="h-3 w-3" /> Connect Account
                    </a>
                ) : (
                    <button
                        onClick={onOpenSettings}
                        className="flex items-center gap-2 border border-white px-6 py-3 text-xs font-bold text-white uppercase hover:bg-white hover:text-black transition-all"
                    >
                        <Settings className="h-3 w-3" /> Configure Credentials
                    </button>
                )}
            </div>
        </div>
    );
};
