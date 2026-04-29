import type { LucideIcon } from 'lucide-react';
import { SurfaceCard } from '@/components/landing/SurfaceCard';

interface ProcessStepProps {
  icon: LucideIcon;
  step: string;
  title: string;
  description: string;
}

export function ProcessStep({
  icon: Icon,
  step,
  title,
  description,
}: ProcessStepProps) {
  return (
    <SurfaceCard className="relative h-full p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-300">
          <Icon className="h-6 w-6" />
        </div>
        <span className="font-mono text-xs text-slate-400 dark:text-slate-500">
          {step}
        </span>
      </div>
      <h3 className="mt-8 text-xl font-semibold tracking-[-0.03em] text-slate-900 dark:text-white">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
        {description}
      </p>
    </SurfaceCard>
  );
}
