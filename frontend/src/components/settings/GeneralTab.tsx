interface GeneralTabProps {
    agentName: string;
    setAgentName: (v: string) => void;
    vaultEnabled: boolean;
    setVaultEnabled: (v: boolean) => void;
    vaultThreshold: number;
    setVaultThreshold: (v: number) => void;
    allowDbWrite: boolean;
    setAllowDbWrite: (v: boolean) => void;
    onSave: () => void;
}

export const GeneralTab = ({ agentName, setAgentName, vaultEnabled, setVaultEnabled, vaultThreshold, setVaultThreshold, allowDbWrite, setAllowDbWrite, onSave }: GeneralTabProps) => (
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
                    <p className="text-xs text-zinc-500">
                        ≈ <span className="text-zinc-300 font-semibold">{Math.round(vaultThreshold / 4).toLocaleString()}</span> tokens
                        <span className="text-zinc-600 ml-1">(at ~4 chars / token)</span>
                    </p>
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

        <div className="space-y-4">
            <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Database Write Access</label>
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-xs text-zinc-600 mt-0.5">
                        When disabled (default), agents are strictly limited to SELECT/SHOW/DESCRIBE queries.
                        When enabled, INSERT/UPDATE/DELETE and other write queries are allowed — but agents must always ask for confirmation before executing them.
                    </p>
                </div>
                <button
                    onClick={() => setAllowDbWrite(!allowDbWrite)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none flex-shrink-0 ml-4 ${allowDbWrite ? 'bg-amber-500' : 'bg-zinc-700'}`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full transition-transform ${allowDbWrite ? 'translate-x-6 bg-black' : 'translate-x-1 bg-zinc-400'}`}
                    />
                </button>
            </div>
            {allowDbWrite && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                    <strong>Write mode active.</strong> Agents MUST ask for explicit user confirmation before running any INSERT, UPDATE, DELETE, DROP, or CREATE queries. This is enforced in the system prompt.
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
