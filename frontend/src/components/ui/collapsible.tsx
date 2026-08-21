"use client";

/**
 * A collapsible panel section.
 *
 * The builder's Shared state and Guardrails panels were always open, which cost
 * the canvas roughly a third of the viewport to show two fields most people set
 * once. Collapsed by default, with a summary in the header so the panel still
 * answers "is anything configured here?" without being opened.
 *
 * On Radix so the closed content is genuinely removed from the accessibility
 * tree and the tab order, rather than hidden with CSS and still reachable by
 * Tab — which is what makes a keyboard user fall into an invisible form.
 */

import * as RCollapsible from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import * as React from "react";

import { cn, focusRing } from "@/lib/cn";

export function Section({
  title,
  description,
  summary,
  defaultOpen = false,
  children,
  className,
}: {
  title: string;
  description?: string;
  /** Shown on the collapsed header — what is inside, without opening it. */
  summary?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = React.useState(defaultOpen);

  return (
    <RCollapsible.Root
      open={open}
      onOpenChange={setOpen}
      className={cn("rounded-lg border border-border bg-surface", className)}
    >
      <RCollapsible.Trigger
        className={cn(
          "flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-surface-2/50",
          focusRing,
          open ? "rounded-t-lg" : "rounded-lg",
        )}
      >
        <ChevronRight
          className={cn(
            "size-4 shrink-0 text-text-faint transition-transform",
            open && "rotate-90",
          )}
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-text">{title}</span>
          {description && (
            <span className="mt-0.5 block text-xs text-text-muted">{description}</span>
          )}
        </span>
        {summary && !open && (
          <span className="shrink-0 text-xs text-text-faint tabular-nums">{summary}</span>
        )}
      </RCollapsible.Trigger>

      <RCollapsible.Content>
        <div className="border-t border-border px-5 py-4">{children}</div>
      </RCollapsible.Content>
    </RCollapsible.Root>
  );
}
