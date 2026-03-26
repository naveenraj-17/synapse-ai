interface GeneralTabProps {
    agentName: string;
    setAgentName: (v: string) => void;
    vaultEnabled: boolean;
    setVaultEnabled: (v: boolean) => void;
    vaultThreshold: number;
    setVaultThreshold: (v: number) => void;
    onSave: () => void;
}

export const GeneralTab = ({ agentName, setAgentName, vaultEnabled, setVaultEnabled, vaultThreshold, setVaultThreshold, onSave }: GeneralTabProps) => (
    <div className="space-y-8">
        <div className="space-y-2">
            <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Global Agent Name</label>
            <input
                type="text"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 p-2.5 text-sm focus:border-white focus:outline-none transition-colors text-white placeholder:text-zinc-700 font-medium"
                placeholder="Enter Agent Name"
            />
            <p className="text-xs text-zinc-600">This name identifies your agent across the system.</p>
        </div>

        <div className="space-y-4">
            <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Large Response Handling</label>
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm text-white font-medium">Save large responses to file</p>
                    <p className="text-xs text-zinc-600 mt-0.5">When enabled, tool outputs exceeding the threshold are saved to a vault file instead of flooding the context.</p>
                </div>
                <button
                    onClick={() => setVaultEnabled(!vaultEnabled)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${vaultEnabled ? 'bg-white' : 'bg-zinc-700'}`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full transition-transform ${vaultEnabled ? 'translate-x-6 bg-black' : 'translate-x-1 bg-zinc-400'}`}
                    />
                </button>
            </div>
            {vaultEnabled && (
                <div className="space-y-2">
                    <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Character Threshold</label>
                    <input
                        type="number"
                        value={vaultThreshold}
                        onChange={(e) => setVaultThreshold(Math.max(1, parseInt(e.target.value) || 1))}
                        className="w-full bg-zinc-900 border border-zinc-800 p-2.5 text-sm focus:border-white focus:outline-none transition-colors text-white placeholder:text-zinc-700 font-medium"
                        min={1}
                    />
                    <p className="text-xs text-zinc-600">Responses longer than this many characters will be saved to a file.</p>
                </div>
            )}
        </div>

        <div className="pt-4 flex justify-end">
            <button
                onClick={onSave}
                className="px-6 py-2.5 text-sm font-bold bg-white text-black hover:bg-zinc-200 transition-all shadow-lg"
            >
                Save Changes
            </button>
        </div>
    </div>
);
