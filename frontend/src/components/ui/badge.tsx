import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]',
  {
    variants: {
      variant: {
        default: 'border-[var(--accent-edge)] bg-[var(--accent-soft)] text-[var(--text-accent)] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
        success: 'border-[rgba(82,211,167,0.22)] bg-[rgba(82,211,167,0.13)] text-emerald-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
        warning: 'border-[rgba(216,154,96,0.24)] bg-[rgba(216,154,96,0.13)] text-amber-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
        danger: 'border-[rgba(228,113,113,0.22)] bg-[rgba(228,113,113,0.13)] text-red-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
        secondary: 'border-[var(--border-soft)] bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] text-[var(--text-secondary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
