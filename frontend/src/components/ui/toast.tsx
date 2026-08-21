"use client";

import { AlertCircle, CheckCircle2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * Transient confirmation.
 *
 * `role="status"` rather than `"alert"`: this is for "Saved", and an assertive
 * live region interrupts whatever a screen reader is mid-sentence on. Errors
 * belong in `ErrorNote`, next to the thing that failed, where they persist.
 */
export function Toast({
  message,
  tone = "success",
  onDismiss,
}: {
  message: string;
  tone?: "success" | "danger";
  onDismiss: () => void;
}) {
  React.useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  if (!message) return null;

  return (
    <div
      role="status"
      className={cn(
        "fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-lg border px-4 py-2.5 text-sm shadow-xl",
        tone === "success"
          ? "border-success/40 bg-success-subtle text-success"
          : "border-danger/40 bg-danger-subtle text-danger",
      )}
    >
      {tone === "success" ? (
        <CheckCircle2 className="size-4 shrink-0" aria-hidden />
      ) : (
        <AlertCircle className="size-4 shrink-0" aria-hidden />
      )}
      {message}
    </div>
  );
}

/** Drives `Toast` without every page re-declaring the same two state hooks. */
export function useToast() {
  const [toast, setToast] = React.useState<{ message: string; tone: "success" | "danger" }>({
    message: "",
    tone: "success",
  });
  const dismiss = React.useCallback(() => setToast((t) => ({ ...t, message: "" })), []);
  const show = React.useCallback(
    (message: string, tone: "success" | "danger" = "success") => setToast({ message, tone }),
    [],
  );
  return { toast, show, dismiss };
}
