import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { ArrowUpRight } from 'lucide-react';
import { SurfaceCard } from '@/components/landing/SurfaceCard';

interface ActionCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  href: string;
  cta: string;
  note: string;
}

export function ActionCard({
  icon: Icon,
  title,
  description,
  href,
  cta,
  note,
}: ActionCardProps) {
  return (
    <SurfaceCard className="flex h-full flex-col p-7">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
        {description}
      </p>
      <p className="mt-4 text-xs uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
        {note}
      </p>
      <Link
        href={href}
        className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-slate-950 transition-colors hover:text-cyan-700 dark:text-white dark:hover:text-cyan-300"
      >
        {cta}
        <ArrowUpRight className="h-4 w-4" />
      </Link>
    </SurfaceCard>
  );
}
