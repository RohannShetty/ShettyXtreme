import { cva, type VariantProps } from "class-variance-authority";
import Root from "./badge.svelte";

export {
  Root,
  //
  Root as Badge,
};

export const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-[2px] border px-1.5 py-px font-mono text-[10px] uppercase tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "border-hairline bg-surface-elevated text-muted-foreground",
        outline: "border-hairline-strong text-muted-foreground",
        secondary: "border-hairline-strong text-body",
        success: "border-success text-success",
        warning: "border-warning text-warning",
        danger: "border-danger text-danger",
        info: "border-info text-info",
        // DESIGN §4 "Badge — conviction": 4-level scale. HIGH uses the amber
        // accent (shadcn alias "primary" = our `--accent`, P5a) — `text-accent`
        // would resolve to surface-elevated and render near-invisible.
        "conviction-low": "border-hairline text-muted-foreground",
        "conviction-medium": "border-warning text-warning",
        "conviction-high": "border-primary text-primary",
        "conviction-extreme": "border-hairline-strong bg-row-selected text-ink",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;
