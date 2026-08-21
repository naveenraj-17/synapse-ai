/**
 * Class composition for the design system.
 *
 * `clsx` alone is not enough once components accept a `className`. It
 * concatenates, and Tailwind's utilities are then resolved by the order they
 * happen to sit in the generated stylesheet — not the order they appear in the
 * string. So `<Button variant="ghost" className="text-danger">`, which is how
 * every destructive row action is written, was only red by luck: `text-danger`
 * and the variant's `text-text-muted` are both single utilities, and whichever
 * Tailwind emitted last won for every call site at once.
 *
 * `twMerge` resolves conflicts by *Tailwind's* semantics — later wins, one
 * winner per property group — so a caller's override is reliable and the
 * primitives below are safe to extend at the point of use.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * The focus ring, in one place.
 *
 * There were three treatments in the codebase — `focus:ring-2`,
 * `focus-visible:ring-2`, and the global `:focus-visible { outline }` — so
 * tabbing across a form changed the shape of the indicator between controls.
 *
 * `focus-visible` rather than `focus`: a mouse click on a button should not
 * leave a ring behind, but a keyboard user must never lose their place. The
 * global outline in `globals.css` stays as the safety net for anything not
 * built from these primitives.
 */
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--bg)]";

/** Focus ring for controls that own a border, which the ring should sit against. */
export const focusRingInset =
  "focus-visible:outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-[var(--ring)]";
