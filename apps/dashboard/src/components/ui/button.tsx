'use client';

import { ReactNode, ButtonHTMLAttributes } from 'react';
import clsx from 'clsx';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'update';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const baseClasses = `
    inline-flex items-center justify-center font-medium
    transition-all duration-200
    focus:outline-none
    border
    tracking-wide
  `;

  const sizeClasses = {
    sm: 'px-4 py-1.5 text-xs gap-1.5',
    md: 'px-6 py-2.5 text-xs gap-2',
    lg: 'px-8 py-3 text-sm gap-2',
  };

  const variantClasses = {
    primary: `
      bg-[rgb(126,170,255)]
      border-[rgb(126,170,255)]
      text-[rgb(10,12,16)]
      hover:bg-[rgb(153,190,255)]
      hover:border-[rgb(153,190,255)]
    `,
    secondary: `
      bg-[rgb(23,27,34)]
      border-[rgb(45,51,62)]
      text-[rgb(201,207,217)]
      hover:border-[rgb(126,170,255)]/60
      hover:text-[rgb(236,239,244)]
    `,
    ghost: `
      bg-transparent
      border-transparent
      text-[rgb(151,160,174)]
      hover:text-[rgb(236,239,244)]
      hover:bg-white/5
    `,
    update: `
      bg-[rgb(126,170,255)]/10
      border-[rgb(126,170,255)]/50
      text-[rgb(153,190,255)]
      hover:bg-[rgb(126,170,255)]/20
      hover:border-[rgb(126,170,255)]
    `,
    danger: `
      bg-rose-500/10
      border-rose-500/50
      text-rose-400
      hover:bg-rose-500/20
      hover:border-rose-500
    `,
  };

  const isDisabled = disabled || loading;

  return (
    <button
      className={clsx(
        baseClasses,
        sizeClasses[size],
        variantClasses[variant],
        isDisabled && 'opacity-50 cursor-not-allowed',
        className
      )}
      disabled={isDisabled}
      {...props}
    >
      {loading && (
        <div className="w-4 h-4 spinner-blue-sm animate-spin" />
      )}
      {!loading && icon && <div className="text-current">{icon}</div>}
      {children}
    </button>
  );
}
