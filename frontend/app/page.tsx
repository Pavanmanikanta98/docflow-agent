import DocumentUploader from '@/components/DocumentUploader';
import { FileText, Cpu, UserCheck, Download, ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface Stat {
  value: string;
  label: string;
  detail: string;
}

interface Step {
  icon: LucideIcon;
  step: string;
  label: string;
  desc: string;
}

const stats: Stat[] = [
  { value: '89%', label: 'Invoice accuracy', detail: 'on 20+ real documents' },
  { value: '85%', label: 'Contract accuracy', detail: 'DeepEval benchmark' },
  { value: '~15%', label: 'HITL flag rate', detail: 'auto-flagged for review' },
];

const steps: Step[] = [
  {
    icon: FileText,
    step: '01',
    label: 'Upload',
    desc: 'Drop any PDF invoice or contract into the zone below.',
  },
  {
    icon: Cpu,
    step: '02',
    label: 'Extract',
    desc: 'Three agents parse, extract and validate every field.',
  },
  {
    icon: UserCheck,
    step: '03',
    label: 'Review',
    desc: 'Low-confidence fields surface for one-click approval.',
  },
  {
    icon: Download,
    step: '04',
    label: 'Export',
    desc: 'Download JSON, CSV or fire a webhook to your system.',
  },
];

export default function Home() {
  return (
    <div className="flex flex-col gap-16 pb-16">

      {/* ── Hero ── */}
      <section
        className="relative -mx-4 md:-mx-8 px-4 md:px-8 pt-16 pb-14 overflow-hidden"
        style={{
          backgroundImage: [
            'linear-gradient(rgba(99,102,241,0.06) 1px, transparent 1px)',
            'linear-gradient(90deg, rgba(99,102,241,0.06) 1px, transparent 1px)',
          ].join(', '),
          backgroundSize: '48px 48px',
        }}
      >
        {/* Soft glow */}
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-[700px] h-[420px] rounded-full opacity-25 dark:opacity-15 blur-3xl pointer-events-none"
          style={{ background: 'radial-gradient(ellipse, #6366f1 0%, transparent 68%)' }}
        />

        <div className="relative max-w-3xl mx-auto text-center">
          <span className="inline-block mb-5 px-3 py-1 rounded-full text-xs font-semibold tracking-widest uppercase bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
            Multi-Agent Document Pipeline
          </span>

          <h1 className="text-4xl md:text-5xl lg:text-[3.5rem] font-bold tracking-tight text-slate-900 dark:text-white leading-[1.1] mb-5">
            Extract structured data
            <br />
            <span className="text-indigo-600 dark:text-indigo-400">
              from any business document
            </span>
          </h1>

          <p className="text-lg text-slate-500 dark:text-slate-400 max-w-xl mx-auto mb-10 leading-relaxed">
            Upload an invoice or contract. Three autonomous agents parse, extract,
            and validate every field — flagging uncertainty for human review before export.
          </p>

          {/* Stat cards */}
          <div className="flex flex-wrap justify-center gap-4">
            {stats.map((s) => (
              <div
                key={s.label}
                className="flex flex-col items-center px-6 py-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm min-w-[148px]"
              >
                <span
                  className="text-3xl font-bold text-slate-900 dark:text-white tabular-nums"
                  style={{ fontFamily: 'var(--font-geist-mono)' }}
                >
                  {s.value}
                </span>
                <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 mt-1.5">
                  {s.label}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  {s.detail}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="max-w-4xl mx-auto w-full">
        <p className="text-center text-xs font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500 mb-8">
          How it works
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {steps.map((item, i) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="relative flex flex-col items-start p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm"
              >
                {i < steps.length - 1 && (
                  <ArrowRight className="hidden md:block absolute -right-3 top-6 w-5 h-5 text-indigo-300 dark:text-indigo-700 z-10" />
                )}
                <span
                  className="text-xs font-bold text-slate-300 dark:text-slate-700 mb-3 tabular-nums"
                  style={{ fontFamily: 'var(--font-geist-mono)' }}
                >
                  {item.step}
                </span>
                <Icon className="w-6 h-6 text-indigo-500 mb-3" />
                <span className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-1">
                  {item.label}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400 leading-snug">
                  {item.desc}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Uploader ── */}
      <section className="max-w-3xl mx-auto w-full">
        <p className="text-center text-xs font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500 mb-6">
          Try it now
        </p>
        <DocumentUploader />
      </section>

    </div>
  );
}
