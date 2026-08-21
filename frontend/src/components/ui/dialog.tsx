"use client";

/**
 * Modal dialog, on Radix.
 *
 * Replaces a hand-rolled version that handled Escape and a backdrop click and
 * nothing else. What it was missing is the part users feel without being able
 * to name it: focus moves into the dialog on open and back to the trigger on
 * close, Tab is trapped inside, the page behind stops scrolling, everything
 * outside is `aria-hidden`, and the whole thing is portalled to `<body>` so no
 * ancestor's `overflow` or stacking context can clip it.
 *
 * `ConfirmDialog` is the destructive-action case, separated because it is the
 * one that must never be easy to fire by accident: the confirm button is not
 * autofocused, so Enter on a keyboard does not delete anything.
 */

import * as RDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

import { Button, buttonStyles } from "./button";

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <RDialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]" />
        <RDialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-xl border border-border-strong bg-surface shadow-2xl focus:outline-none",
            { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" }[size],
          )}
        >
          <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <RDialog.Title className="text-sm font-semibold text-text">
                {title}
              </RDialog.Title>
              {description && (
                <RDialog.Description className="mt-1 text-sm text-text-muted">
                  {description}
                </RDialog.Description>
              )}
            </div>
            <RDialog.Close
              aria-label="Close"
              className={cn(
                buttonStyles({ variant: "ghost", size: "sm", iconOnly: true }),
                "-mr-1.5 -mt-1 text-text-faint",
              )}
            >
              <X className="size-4" aria-hidden />
            </RDialog.Close>
          </header>

          {children && <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>}

          {footer && (
            <footer className="flex justify-end gap-2 border-t border-border px-5 py-4">
              {footer}
            </footer>
          )}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Delete",
  busy,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  busy?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          {/*
            Deliberately not autofocused. Radix focuses the first tabbable
            element on open, and if that were the destructive button, a user
            who opened this by pressing Enter would delete on the key-up.
          */}
          <Button variant="danger" onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
