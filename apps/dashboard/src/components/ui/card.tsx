'use client';

import { ReactNode, MouseEventHandler } from 'react';
import clsx from 'clsx';

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'glass' | 'gradient';
  padding?: 'sm' | 'md' | 'lg';
  onClick?: MouseEventHandler<HTMLDivElement>;
}

export function Card({
  children,
  className,
  variant = 'default',
  padding = 'md',
  onClick,
}: CardProps) {
  const paddingClasses = {
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  };

  const variantClasses = {
    default: `
      bg-[rgb(17,20,26)]
      border border-[rgb(35,40,49)]
    `,
    glass: `
      bg-[rgb(17,20,26)]
      border border-[rgb(35,40,49)]
    `,
    gradient: `
      bg-[rgb(23,27,34)]
      border border-[rgb(45,51,62)]
    `,
  };

  return (
    <div
      className={clsx(
        'relative transition-all duration-300',
        variantClasses[variant],
        paddingClasses[padding],
        'rounded-lg hover:border-[rgb(65,73,87)]',
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
}

export function MetricCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  className,
}: MetricCardProps) {
  const trendColors = {
    up: 'text-emerald-400',
    down: 'text-red-400',
    neutral: 'text-gray-400',
  };

  return (
    <Card
      variant="glass"
      className={clsx(
        'group transition-all duration-300 hover:translate-y-[-2px]',
        'border-l-2 border-l-[rgb(126,170,255)]/70',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            {icon && <div className="text-[rgb(151,160,174)]">{icon}</div>}
            <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[rgb(151,160,174)]">
              {title}
            </span>
          </div>
          <div className="text-3xl font-semibold text-[rgb(236,239,244)]">
            {value}
          </div>
          {subtitle && (
            <p className={clsx('text-xs mt-1', trend ? trendColors[trend] : 'text-[rgb(100,100,120)]')}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
