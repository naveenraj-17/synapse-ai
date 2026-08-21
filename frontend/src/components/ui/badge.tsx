/**
 * Badges and tags.
 *
 * A badge states what something *is* — a role, a plan, a step type. A tag is a
 * value someone attached and can take off again.
 *
 * `whitespace-nowrap` matters more than it sounds: these sit in table cells
 * that shrink, and a two-word badge breaking across lines takes the row height
 * with it and makes one row taller than its neighbours.
 */

import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "accent" | "danger" | "warning" | "success";

const TONES: Record<BadgeTone, { chip: string; dot: string }> = {
  neutral: { chip: "bg-surface-2 text-text-muted", dot: "bg-text-faint" },
  accent: { chip: "bg-accent-subtle text-accent", dot: "bg-accent" },
  danger: { chip: "bg-danger-subtle text-danger", dot: "bg-danger" },
  warning: { chip: "bg-warning-subtle text-warning", dot: "bg-warning" },
  success: { chip: "bg-success-subtle text-success", dot: "bg-success" },
};

export function Badge({
  children,
  tone = "neutral",
  size = "md",
  dot = false,
  className,
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  size?: "sm" | "md";
  /** A coloured dot before the label, for when the tone alone is too quiet. */
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 whitespace-nowrap rounded-md font-medium",
        size === "md" ? "px-2 py-0.5 text-xs" : "px-1.5 py-0.5 text-[0.6875rem]",
        TONES[tone].chip,
        className,
      )}
    >
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full", TONES[tone].dot)} aria-hidden />}
      <span className="truncate">{children}</span>
    </span>
  );
}

/** A value someone attached: outlined rather than filled, and removable. */
export function Tag({
  children,
  onRemove,
  className,
}: {
  children: React.ReactNode;
  onRemove?: () => void;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-md border border-border-strong bg-surface py-0.5 pl-2 text-xs text-text-muted",
        onRemove ? "pr-1" : "pr-2",
        className,
      )}
    >
      <span className="truncate">{children}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${typeof children === "string" ? children : "tag"}`}
          className="rounded-md p-0.5 text-text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <X className="size-3" aria-hidden />
        </button>
      )}
    </span>
  );
}
