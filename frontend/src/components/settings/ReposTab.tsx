import React, { useState, useEffect } from 'react';
import { Plus, Trash2, FolderGit2, RefreshCw } from 'lucide-react';
import { ConfirmationModal } from './ConfirmationModal';

export interface Repo {
    id: string;
    name: string;
    path: string;
    description: string;
    included_patterns: string[];
    excluded_patterns: string[];
    last_indexed: string | null;
    status: string;
    file_count: number;
}

export function ReposTab() {
    const [repos, setRepos] = useState<Repo[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [draftRepo, setDraftRepo] = useState<Partial<Repo> | null>(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

    useEffect(() => {
        fetchRepos();
        const interval = setInterval(fetchRepos, 5000); // Polling for index status updates
        return () => clearInterval(interval);
    }, []);

    const fetchRepos = async () => {
        try {
            const res = await fetch('/api/repos');
            if (res.ok) {
                const data = await res.json();
                setRepos(data);
            }
        } catch (error) {
            console.error('Failed to fetch repos', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSaveRepo = async () => {
        if (!draftRepo?.name || !draftRepo?.path) {
            alert("Name and Path are required.");
            return;
        }

        const newRepo = {
            id: draftRepo.id || "repo_" + Date.now(),
            name: draftRepo.name,
            path: draftRepo.path,
            description: draftRepo.description || "",
            included_patterns: draftRepo.included_patterns || ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.rs", "*.go", "*.java", "*.md", "*.html", "*.vue", "*.css", "*.scss", "*.cpp", "*.c"],
            excluded_patterns: draftRepo.excluded_patterns || [".*", "node_modules", "__pycache__", "venv", ".git", "*.pyc", ".next", "dist", "build", "coverage", ".idea", ".vscode"],
            status: draftRepo.status || "pending",
            file_count: draftRepo.file_count || 0
        };

        try {
            const res = await fetch('/api/repos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newRepo)
            });
            if (res.ok) {
                alert(draftRepo.id ? "Repo updated!" : "Repo added!");
                setDraftRepo(null);
                fetchRepos();
            } else {
                alert("Failed to save repo.");
            }
        } catch (error) {
            console.error('Save error', error);
            alert("Failed to save repo.");
        }
    };

    const handleDeleteRepo = async (id: string) => {
        try {
            const res = await fetch(`/api/repos/${id}`, { method: 'DELETE' });
            if (res.ok) {
                alert("Repo deleted.");
                fetchRepos();
            }
        } catch (error) {
            alert("Failed to delete repo.");
        }
    };

    const handleReindex = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            const res = await fetch(`/api/repos/${id}/reindex`, { method: 'POST' });
            if (res.ok) {
                alert("Indexing started...");
                fetchRepos();
            } else {
                // Read the error strictly textually avoiding HTML injection
                const textDetail = await res.text();
                alert(`Re-index failed: ${textDetail}`);
            }
        } catch (error) {
            alert("Re-index failed.");
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'indexed': return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
            case 'indexing': return 'bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse';
            case 'error': return 'bg-red-500/10 text-red-500 border-red-500/20';
            default: return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
        }
    };

    if (isLoading) return <div className="p-8 text-center text-zinc-500">Loading...</div>;

    if (draftRepo !== null) {
        return (
            <div className="space-y-8">
                <div className="mb-4">
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <FolderGit2 className="h-5 w-5" />
                        {draftRepo.id ? 'Edit Repo' : 'Add New Repo'}
                    </h3>
                    <p className="text-zinc-500 text-sm mt-1">Configure codebase indexing settings.</p>
                </div>

                <div className="space-y-4">
                    <div className="space-y-2">
                        <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Repo Name</label>
                        <input
                            type="text"
                            value={draftRepo.name || ''}
                            onChange={(e) => setDraftRepo({ ...draftRepo, name: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none transition-colors font-mono"
                            placeholder="e.g. Frontend App"
                            autoComplete="off"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Absolute Directory Path</label>
                        <input
                            type="text"
                            value={draftRepo.path || ''}
                            onChange={(e) => setDraftRepo({ ...draftRepo, path: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none transition-colors font-mono"
                            placeholder="/home/user/projects/app"
                            autoComplete="off"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs uppercase font-bold text-zinc-500 tracking-wider">Interconnection Description</label>
                        <textarea
                            value={draftRepo.description || ''}
                            onChange={(e) => setDraftRepo({ ...draftRepo, description: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 p-3 text-sm text-white focus:border-white focus:outline-none transition-colors font-mono min-h-[100px]"
                            placeholder="Help the LLM understand what this repo contains and how it interacts with other repos..."
                        />
                    </div>
                    <div className="flex gap-4 justify-end pt-4">
                        <button
                            onClick={() => setDraftRepo(null)}
                            className="px-6 py-2.5 text-sm font-bold text-zinc-400 hover:text-white transition-all"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSaveRepo}
                            className="px-6 py-2.5 text-sm font-bold bg-white text-black hover:bg-zinc-200 transition-all shadow-lg"
                        >
                            Save Repository
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            <div className="mb-4 flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <FolderGit2 className="h-5 w-5" />
                        Code Repositories
                    </h3>
                    <p className="text-zinc-500 text-sm mt-1">Manage your agent's codebases for semantic code searching.</p>
                </div>
                <button
                    onClick={() => setDraftRepo({})}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-white text-black hover:bg-zinc-200 transition-all shadow-lg"
                >
                    <Plus className="w-4 h-4" /> Add Repo
                </button>
            </div>

            {repos.length === 0 ? (
                <div className="text-center py-12 border border-dashed border-zinc-800 bg-zinc-900/50">
                    <FolderGit2 className="w-8 h-8 mx-auto text-zinc-600 mb-3" />
                    <h3 className="text-sm font-bold text-zinc-100">No repositories indexed</h3>
                    <p className="text-sm text-zinc-500 mt-1 mb-6">Add a local repository path to enable code context.</p>
                    <button
                        onClick={() => setDraftRepo({})}
                        className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-bold bg-white text-black hover:bg-zinc-200 transition-all shadow-lg"
                    >
                        <Plus className="w-4 h-4" /> Add Repository
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4">
                    {repos.map((repo) => (
                        <div
                            key={repo.id}
                            className="p-4 border border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 transition-colors cursor-pointer group"
                            onClick={() => setDraftRepo(repo)}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <h4 className="font-bold text-white text-lg flex items-center gap-2">
                                        {repo.name}
                                        <span className={`text-[10px] font-bold px-2 py-0.5 border uppercase tracking-wide ${getStatusColor(repo.status)}`}>
                                            {repo.status}
                                        </span>
                                    </h4>
                                    <p className="text-xs text-zinc-500 font-mono truncate max-w-lg mt-1">{repo.path}</p>
                                </div>
                                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button
                                        onClick={(e) => handleReindex(repo.id, e)}
                                        className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                                        title="Re-Index"
                                    >
                                        <RefreshCw className={`w-4 h-4 ${repo.status === 'indexing' ? 'animate-spin text-white' : ''}`} />
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setConfirmDeleteId(repo.id);
                                        }}
                                        className="p-2 text-zinc-400 hover:text-red-500 hover:bg-red-500/10 transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                            {repo.description && (
                                <p className="text-sm text-zinc-400 mt-3 line-clamp-2">
                                    {repo.description}
                                </p>
                            )}
                            <div className="flex gap-4 mt-4 text-xs font-bold text-zinc-600 uppercase tracking-wider">
                                <span>{repo.file_count || 0} CHUNKS INDEXED</span>
                                {repo.last_indexed && (
                                    <span>• UPDATED {new Date(repo.last_indexed).toLocaleString()}</span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <ConfirmationModal
                isOpen={!!confirmDeleteId}
                title="Delete Repository"
                message="Are you sure you want to delete this repository and its index? This action cannot be undone."
                onConfirm={() => {
                    if (confirmDeleteId) handleDeleteRepo(confirmDeleteId);
                    setConfirmDeleteId(null);
                }}
                onClose={() => setConfirmDeleteId(null)}
            />
        </div>
    );
}
