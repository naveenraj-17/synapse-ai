"use client";

/**
 * Checkbox, including the indeterminate state a "select all" header needs.
 *
 * `indeterminate` is not an attribute — on a native input it can only be set
 * from JavaScript on the DOM node, which is why hand-rolled tables so often
 * show a *checked* header box when only some rows are selected. Radix models it
 * as a third value (`"indeterminate"`) and sets `aria-checked="mixed"`, so the
 * visual and the announced state agree.
 */

import * as RCheckbox from "@radix-ui/react-checkbox";
import { Check, Minus } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

export type CheckedState = boolean | "indeterminate";

export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
  className,
}: {
  checked: CheckedState;
  onChange: (checked: boolean) => void;
  /** Required: an unlabelled checkbox in a table row is unusable by screen reader. */
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <RCheckbox.Root
      checked={checked}
      onCheckedChange={(next) => onChange(next === true)}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
        "border-border-strong bg-surface hover:border-accent",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        "data-[state=checked]:border-accent data-[state=checked]:bg-accent",
        "data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent",
        "disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
    >
      <RCheckbox.Indicator className="text-accent-fg">
        {checked === "indeterminate" ? (
          <Minus className="size-3" strokeWidth={3} aria-hidden />
        ) : (
          <Check className="size-3" strokeWidth={3} aria-hidden />
        )}
      </RCheckbox.Indicator>
    </RCheckbox.Root>
  );
}
