import { cva, type VariantProps } from "class-variance-authority";
import Root from "./button.svelte";

export {
  Root,
  //
  Root as Button,
};

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[4px] text-[13px] font-semibold tracking-[0.02em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 outline-none",
  {
    variants: {
      variant: {
        default: "bg-accent text-on-accent hover:bg-accent-active",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        danger: "bg-danger text-white hover:bg-[#ff5f64] disabled:bg-[#7a2a2e] disabled:text-[#ffb9bb]",
        outline: "border border-hairline-strong bg-background hover:bg-surface-elevated hover:text-ink",
        secondary: "bg-surface-elevated text-body border border-hairline-strong hover:border-muted-foreground hover:text-ink",
        ghost: "hover:bg-row-hover hover:text-ink",
        link: "text-accent underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-6 py-1.5 has-[>svg]:px-3",
        sm: "h-7 rounded-[4px] gap-1.5 px-3 has-[>svg]:px-2.5",
        lg: "h-9 rounded-[4px] px-8 has-[>svg]:px-4",
        icon: "size-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;
export type ButtonSize = NonNullable<VariantProps<typeof buttonVariants>["size"]>;
