"use client";

/**
 * The row overflow menu — the `⋮` at the end of a table row.
 *
 * On Radix rather than a `useState` popover, for the parts that are invisible
 * until they are missing: it closes on outside click *and* on scroll, returns
 * focus to the trigger, traps arrow-key navigation, supports type-ahead, and
 * portals out of the table so `overflow-x: auto` on the scroll container cannot
 * clip it. That last one is the specific reason a hand-rolled menu inside a
 * scrollable table nearly always ends up half-hidden.
 */

import * as RMenu from "@radix-ui/react-dropdown-menu";
import { MoreVertical } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

import { buttonStyles } from "./button";

export function RowMenu({
  children,
  label = "More actions",
}: {
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <RMenu.Root>
      <RMenu.Trigger
        aria-label={label}
        className={cn(
          buttonStyles({ variant: "ghost", iconOnly: true }),
          "text-text-faint data-[state=open]:bg-surface-2 data-[state=open]:text-text",
        )}
      >
        <MoreVertical className="size-4" aria-hidden />
      </RMenu.Trigger>
      <RMenu.Portal>
        <RMenu.Content
          align="end"
          sideOffset={4}
          className="z-50 min-w-44 overflow-hidden rounded-lg border border-border-strong bg-surface p-1 shadow-xl"
        >
          {children}
        </RMenu.Content>
      </RMenu.Portal>
    </RMenu.Root>
  );
}

export function MenuItem({
  children,
  onSelect,
  icon: Icon,
  tone = "default",
  disabled,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "danger";
  disabled?: boolean;
}) {
  return (
    <RMenu.Item
      disabled={disabled}
      // Radix restores focus to the trigger on close, which fights a dialog
      // opened from the same click — the dialog steals focus, then the menu
      // takes it back. Deferring a tick lets the menu finish closing first.
      onSelect={(e) => {
        e.preventDefault();
        setTimeout(onSelect, 0);
      }}
      className={cn(
        "flex cursor-pointer select-none items-center gap-2.5 rounded px-2 py-1.5 text-sm outline-none",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-45",
        tone === "danger"
          ? "text-danger data-[highlighted]:bg-danger-subtle"
          : "text-text data-[highlighted]:bg-surface-2",
      )}
    >
      {Icon && <Icon className="size-4 shrink-0" aria-hidden />}
      {children}
    </RMenu.Item>
  );
}

export function MenuSeparator() {
  return <RMenu.Separator className="my-1 h-px bg-border" />;
}

export function MenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <RMenu.Label className="px-2 py-1.5 text-xs font-medium text-text-faint">
      {children}
    </RMenu.Label>
  );
}
