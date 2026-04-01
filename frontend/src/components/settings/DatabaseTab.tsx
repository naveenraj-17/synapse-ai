import { Database } from 'lucide-react';

interface DatabaseTabProps {
    sqlConnectionString: string;
    setSqlConnectionString: (v: string) => void;
    onSave: () => void;
}

export const DatabaseTab = ({ sqlConnectionString, setSqlConnectionString, onSave }: DatabaseTabProps) => (
    <div className="space-y-8">
        <div className="mb-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Database className="h-5 w-5" />
                SQL Database Connection
            </h3>
            <p className="text-zinc-500 text-sm mt-1">
                Connect your agent to a SQL database (PostgreSQL, MySQL, SQLite) to enable business intelligence capabilities.
            </p>
        </div>

        <div className="space-y-4">
            <div className="space-y-2">
                <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Connection String (SQLAlchemy URL)</label>
                <input
                    type="password"
                    value={sqlConnectionString}
                    onChange={(e) => setSqlConnectionString(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none transition-colors font-mono"
                    placeholder="postgresql://user:password@localhost:5432/dbname"
                />
                <p className="text-xs text-zinc-600">
                    Format: <code>dialect+driver://username:password@host:port/database</code><br />
                    Examples:<br />
                    - Postgres: <code>postgresql://scott:tiger@localhost/test</code><br />
                    - MySQL: <code>mysql+pymysql://user:pass@localhost/foo</code><br />
                    - SQLite: <code>sqlite:///foo.db</code>
                </p>
            </div>

            <div className="p-4 bg-zinc-900/50 border border-zinc-800 text-xs text-zinc-400">
                <strong>Security Note:</strong> The agent will have access to execute queries. Use a read-only user if possible.
            </div>
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
