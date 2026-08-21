"use client";

/**
 * Form controls.
 *
 * **`block` is the bug fix here.** An `<input>` is `inline-block`, so two of
 * them with a width that leaves room on the line sit *side by side*. That is
 * what put the orchestration description alongside the title instead of under
 * it: both were `w-full max-w-2xl` — 672px each in a 1600px column — so the
 * browser did exactly what it was asked and laid them out as a row. Every
 * control here is `block`, which makes that layout impossible to write by
 * accident.
 *
 * `"use client"`: `Field` needs `useId` to point a hint at the control it
 * describes, and `SearchInput` owns a clear button.
 */

import { Search, X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

import { controlStyles, type ControlSize } from "./control-styles";

export function Input({
  className,
  size = "md",
  invalid,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & {
  size?: ControlSize;
  invalid?: boolean;
}) {
  return (
    <input
      {...props}
      aria-invalid={invalid || undefined}
      className={cn(controlStyles({ size, invalid }), className)}
    />
  );
}

export function Textarea({
  className,
  size = "md",
  invalid,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  size?: ControlSize;
  invalid?: boolean;
}) {
  return (
    <textarea
      {...props}
      aria-invalid={invalid || undefined}
      className={cn(controlStyles({ size, invalid }), "resize-y", className)}
    />
  );
}

/**
 * Label, control, and the sentence underneath.
 *
 * The `<label>` wraps the control, which associates the two without either
 * needing an id — and works for the Radix select trigger too, since a `<button>`
 * is a labelable element. What it could not do is associate the *hint*: it was
 * grey text near a field, invisible to a screen reader. So the hint and error
 * get ids, and `aria-describedby` is threaded onto the child.
 */
export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string;
  hint?: string;
  /** Replaces the hint while set, and marks the control invalid. */
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const id = React.useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, errorId ? undefined : hintId].filter(Boolean).join(" ") || undefined;

  // Threaded rather than required as a prop on every call site: `<Field><Input/></Field>`
  // is the shape all twenty-odd forms already use, and this keeps it.
  const control = React.isValidElement<{
    "aria-describedby"?: string;
    "aria-invalid"?: boolean;
    invalid?: boolean;
  }>(children)
    ? React.cloneElement(children, {
        "aria-describedby":
          [children.props["aria-describedby"], describedBy].filter(Boolean).join(" ") || undefined,
        ...(error ? { invalid: true } : {}),
      })
    : children;

  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 block text-sm font-medium text-text">
        {label}
        {required && (
          <span className="ml-0.5 text-danger" aria-hidden>
            *
          </span>
        )}
      </span>
      {control}
      {error ? (
        <span id={errorId} role="alert" className="mt-1.5 block text-xs text-danger">
          {error}
        </span>
      ) : (
        hint && (
          <span id={hintId} className="mt-1.5 block text-xs leading-relaxed text-text-faint">
            {hint}
          </span>
        )
      )}
    </label>
  );
}

/**
 * The search box that sits above a list.
 *
 * The icon, its padding offset and the clear button were assembled inline in
 * `DataTable`. Extracted so the filter box on a hand-written screen is the same
 * control, down to where the X lands.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "size"> & {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className={cn("relative w-full max-w-xs", className)}>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-text-faint"
        aria-hidden
      />
      <Input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={props["aria-label"] ?? placeholder}
        {...props}
        // `[&::-webkit-search-cancel-button]:hidden` — WebKit draws its own X
        // on `type="search"`, which would sit beside ours.
        className="py-1.5 pl-8 pr-8 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-text-faint transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
