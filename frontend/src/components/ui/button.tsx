import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-[18px] text-sm font-medium transition-all duration-150 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'border border-[var(--accent-edge)] bg-[linear-gradient(135deg,var(--accent),var(--accent-strong))] text-[#06111c] shadow-[0_22px_40px_rgba(var(--accent-rgb),0.22)] hover:-translate-y-0.5 hover:brightness-[1.03]',
        destructive: 'border border-[rgba(197,63,63,0.26)] bg-[linear-gradient(135deg,#dc7373,#bd4b4b)] text-white shadow-[0_18px_34px_rgba(197,63,63,0.2)] hover:-translate-y-0.5 hover:brightness-105',
        outline: 'border border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.035),rgba(255,255,255,0.01))] text-[var(--text-secondary)] hover:-translate-y-0.5 hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
        ghost: 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
        link: 'underline-offset-4 hover:underline text-[var(--text-accent)]',
      },
      size: {
        default: 'h-10 px-4 py-2 text-sm',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-11 px-5',
        icon: 'h-10 w-10 rounded-[18px]',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
