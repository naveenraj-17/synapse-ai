/*
 * One page frame for every screen in the app.
 *
 * Before this, four of the work tabs rendered their own <h1> with hand-written
 * copy and the rest got "Manage your agent's {activeTab} configuration." from a
 * template. Title and blurb are passed in now, so there is exactly one header
 * implementation and one place per product that decides the words.
 *
 * It takes `title` and `description` as plain strings rather than a nav entry.
 * That is deliberate and it is what lets this live in the kit: a `nav: NavEntry`
 * prop would drag one product's navigation model into a design system the other
 * product also consumes, and the two products' navigations genuinely differ —
 * different sections, different landing page, different second level. Each
 * keeps its own `lib/nav.ts` and unpacks it at the call site.
 *
 * No "use client" — it renders no hooks, so it works from a server page and
 * from inside a client tree alike.
 */
import { cn } from "@/lib/cn";

import { PageHeader } from "./text";

/**
 * How wide the content column is allowed to get.
 *
 * `form` is the default because most screens are a column of prose and controls,
 * and a form line longer than about 64rem stops scanning as a line. `wide` is
 * for screens whose content is genuinely tabular: a six-column row needs the
 * width, and capping it puts the row's name at the far left and the action it
 * applies to 160mm away on the right.
 */
export type ScreenWidth = "form" | "wide";

const WIDTHS: Record<ScreenWidth, string> = {
  form: "max-w-5xl",
  wide: "max-w-[88rem]",
};

export function Screen({
  title,
  description,
  actions,
  breadcrumb,
  bleed = false,
  width = "form",
  children,
}: {
  title: React.ReactNode;
  /**
   * One line, shown under the title. Never a template.
   *
   * A node rather than a string because a detail page's subtitle is often the
   * thing being detailed — a run id in `Mono`, not a sentence.
   */
  description?: React.ReactNode;
  /** Right-hand side of the header — a button, or a close control. */
  actions?: React.ReactNode;
  /** Sits above the title: a back link on a detail page. */
  breadcrumb?: React.ReactNode;
  /**
   * For screens that manage their own height — the DAG canvas, the log
   * viewer, the file explorer. Gives them a flex column to fill instead of a
   * scroll container to overflow. `width` does not apply: a bleeding screen
   * owns its own layout all the way to the edges.
   */
  bleed?: boolean;
  width?: ScreenWidth;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/*
        The rule is full-bleed and the header's *content* is not: it sits in the
        same column the body does, at the same horizontal padding, so the title
        starts exactly above the first thing under it. Centring the body inside
        a max-width while the title stayed at the page edge left the two
        visibly out of line at wide viewports — the heading floating alone off
        to the left of everything it heads.

        The header itself is the kit's own `PageHeader`, so a screen here and a
        screen in the other product are the same object.
      */}
      <header className="shrink-0 border-b border-border">
        <div className={cn("mx-auto w-full px-6 py-4 md:px-12", !bleed && WIDTHS[width])}>
          <PageHeader title={title} description={description} actions={actions}>
            {breadcrumb}
          </PageHeader>
        </div>
      </header>

      {bleed ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className={cn("mx-auto w-full space-y-10 px-6 py-6 md:px-12 md:py-12", WIDTHS[width])}>
            {children}
          </div>
        </div>
      )}
    </div>
  );
}
