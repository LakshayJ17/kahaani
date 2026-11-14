import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/*
  Storybook buttons: chunky rounded rectangles that sit on a thicker bottom edge and press
  down when clicked. Saffron with dark ink is the one main action on a screen.
*/
type Variant = "primary" | "secondary" | "quiet";

const base =
  "inline-flex min-h-12 select-none items-center justify-center gap-2.5 whitespace-nowrap rounded-xl px-5 text-body font-semibold transition-[background-color,box-shadow,transform] duration-150 ease-out active:translate-y-[2px] disabled:pointer-events-none disabled:opacity-45";

const variants: Record<Variant, string> = {
  primary:
    "bg-saffron text-ink shadow-[0_3px_0_var(--saffron-deep)] hover:bg-[#f5b04f] active:shadow-[0_1px_0_var(--saffron-deep)]",
  secondary:
    "bg-page text-ink ring-1 ring-ink/20 shadow-[0_3px_0_rgb(43_33_24_/_0.18)] hover:bg-[#fff6e3] active:shadow-[0_1px_0_rgb(43_33_24_/_0.18)]",
  quiet:
    "min-h-11 px-2 font-medium underline decoration-ink/30 underline-offset-4 hover:decoration-ink",
};

type Common = {
  variant?: Variant;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
};

const cls = (variant: Variant, extra: string) =>
  `${base} ${variants[variant]} ${extra}`;

export function Button({
  variant = "primary",
  icon,
  className = "",
  children,
  ...props
}: Common & ComponentProps<"button">) {
  return (
    <button {...props} className={cls(variant, className)}>
      {icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "primary",
  icon,
  className = "",
  children,
  ...props
}: Common & ComponentProps<typeof Link>) {
  return (
    <Link {...props} className={cls(variant, className)}>
      {icon}
      {children}
    </Link>
  );
}

export function ButtonAnchor({
  variant = "primary",
  icon,
  className = "",
  children,
  ...props
}: Common & ComponentProps<"a">) {
  return (
    <a {...props} className={cls(variant, className)}>
      {icon}
      {children}
    </a>
  );
}
