/**
 * The bordered panel every screen is assembled from.
 *
 * `Card` deliberately does not pad its children: half the cards on the site
 * hold a table that must reach the border. So the padding lived at the call
 * sites instead, where it became `px-5 py-4`, `px-5 pb-5`, `p-5` and
 * `space-y-4 px-5 py-4` across fourteen of them. `CardBody` is that padding,
 * named once.
 */

import * as React from "react";

import { cn } from "@/lib/cn";

export function Card({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  /** Right-hand side of the header — usually one button. */
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("overflow-hidden rounded-lg border border-border bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-text">{title}</h2>}
            {description && (
              <p className="mt-1 text-sm leading-relaxed text-text-muted">{description}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

export function CardFooter({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
