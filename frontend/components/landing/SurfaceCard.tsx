import type { HTMLAttributes, ReactNode } from 'react';

interface SurfaceCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function SurfaceCard({
  children,
  className = '',
  ...props
}: SurfaceCardProps) {
  return (
    <div
      {...props}
      className={[
        'rounded-[28px] border border-white/60 bg-white/80 shadow-[0_24px_80px_-36px_rgba(14,116,144,0.45)] backdrop-blur-xl',
        'dark:border-white/10 dark:bg-slate-950/70',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  );
}
