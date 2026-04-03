"use client";

import { useState } from "react";
import { Download, Upload } from "lucide-react";
import { ExportView } from "./import-export/ExportView";
import { ImportView } from "./import-export/ImportView";

export function ImportExportTab() {
  const [view, setView] = useState<"export" | "import">("export");

  return (
    <div className="space-y-8">
      {/* View toggle — matches McpServersTab stdio/remote toggle */}
      <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 p-1 w-fit">
        <button
          onClick={() => setView("export")}
          className={`flex items-center gap-1.5 px-5 py-2 text-xs font-bold transition-colors ${view === "export" ? "bg-white text-black" : "text-zinc-500 hover:text-white"}`}
        >
          <Download className="h-3.5 w-3.5" /> Export
        </button>
        <button
          onClick={() => setView("import")}
          className={`flex items-center gap-1.5 px-5 py-2 text-xs font-bold transition-colors ${view === "import" ? "bg-white text-black" : "text-zinc-500 hover:text-white"}`}
        >
          <Upload className="h-3.5 w-3.5" /> Import
        </button>
      </div>

      {view === "export" ? <ExportView /> : <ImportView />}
    </div>
  );
}
