import Link from 'next/link';
import DocumentUploader from '@/components/DocumentUploader';
import { ActionCard } from '@/components/landing/ActionCard';
import { ProcessStep } from '@/components/landing/ProcessStep';
import { SectionHeading } from '@/components/landing/SectionHeading';
import { SurfaceCard } from '@/components/landing/SurfaceCard';
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  Cable,
  ChartNoAxesCombined,
  CheckCircle2,
  Cpu,
  Download,
  FileSearch,
  FileText,
  HandCoins,
  MessageSquareMore,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
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

interface Signal {
  title: string;
  desc: string;
  icon: LucideIcon;
}

interface Capability {
  title: string;
  desc: string;
  icon: LucideIcon;
  accent: string;
  className?: string;
}

interface FinalAction {
  title: string;
  desc: string;
  icon: LucideIcon;
  href: string;
  cta: string;
  note: string;
}

const stats: Stat[] = [
  { value: '—', label: 'Invoice accuracy', detail: 'Tracked after deploy' },
  { value: '—', label: 'Contract accuracy', detail: 'DeepEval suite pending' },
  { value: '—', label: 'HITL flag rate', detail: 'Measured in production' },
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

const signals: Signal[] = [
  {
    title: 'Product-led first impression',
    desc: 'The upload box is the hero. Visitors understand the workflow before they read a single feature grid.',
    icon: FileSearch,
  },
  {
    title: 'Human review stays in the story',
    desc: 'This is not generic OCR. Confidence scoring and human approval are core to the product and should stay visible.',
    icon: UserCheck,
  },
  {
    title: 'Technical depth without clutter',
    desc: 'Developer buyers want proof. The page should show agent orchestration, exports, privacy, and extension paths without feeling academic.',
    icon: Cpu,
  },
];

const capabilities: Capability[] = [
  {
    title: 'Parser agent',
    desc: 'Detects document type, normalizes the raw content, and prepares the extraction graph.',
    icon: Bot,
    accent: 'from-cyan-500/20 via-sky-500/10 to-transparent',
    className: 'md:col-span-2',
  },
  {
    title: 'Extractor + validator',
    desc: 'Typed schemas, field-level confidence, and structured outputs keep results operational instead of approximate.',
    icon: ShieldCheck,
    accent: 'from-emerald-500/20 via-teal-500/10 to-transparent',
  },
  {
    title: 'Review-ready output',
    desc: 'Low-confidence values route into a review queue so humans only touch what actually needs attention.',
    icon: CheckCircle2,
    accent: 'from-amber-500/20 via-orange-500/10 to-transparent',
  },
  {
    title: 'Export layer',
    desc: 'Clean JSON, CSV, or webhook delivery gives the pipeline a real destination inside your system.',
    icon: Cable,
    accent: 'from-fuchsia-500/20 via-purple-500/10 to-transparent',
    className: 'md:col-span-2',
  },
];

const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? 'contact@yourdomain.com';

const finalActions: FinalAction[] = [
  {
    title: 'Custom implementation',
    desc: 'Need invoices, contracts, or a custom document type wired into your existing workflow? Get in touch to discuss scope and timeline.',
    icon: MessageSquareMore,
    href: `mailto:${CONTACT_EMAIL}`,
    cta: 'Send a message',
    note: 'Response within 24 hours',
  },
  {
    title: 'Extend DocFlow',
    desc: 'The plugin architecture means adding a new document type is a single file. Propose an extension or request a new document type.',
    icon: ChartNoAxesCombined,
    href: `mailto:${CONTACT_EMAIL}`,
    cta: 'Request an extension',
    note: 'Open to collaboration',
  },
  {
    title: 'Support the project',
    desc: 'DocFlow is open source. If it saved you time or inspired your own pipeline, consider supporting further development.',
    icon: HandCoins,
    href: 'https://buymeacoffee.com/replace-me',
    cta: 'Buy me a coffee',
    note: 'Update link before deploy',
  },
];

export default function Home() {
  return (
    <div className="relative flex flex-col gap-24 pb-24">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[760px] overflow-hidden">
        <div className="absolute left-1/2 top-[-12rem] h-[32rem] w-[32rem] -translate-x-[72%] rounded-full bg-cyan-300/30 blur-3xl dark:bg-cyan-500/15" />
        <div className="absolute right-[-8rem] top-[7rem] h-[28rem] w-[28rem] rounded-full bg-fuchsia-300/20 blur-3xl dark:bg-fuchsia-500/10" />
        <div
          className="absolute inset-x-0 top-0 h-full opacity-60 dark:opacity-40"
          style={{
            backgroundImage: [
              'linear-gradient(rgba(14,165,233,0.09) 1px, transparent 1px)',
              'linear-gradient(90deg, rgba(14,165,233,0.09) 1px, transparent 1px)',
            ].join(', '),
            backgroundSize: '72px 72px',
            maskImage: 'linear-gradient(to bottom, black 55%, transparent 100%)',
          }}
        />
      </div>

      <section
        id="top"
        className="relative -mx-4 overflow-hidden px-4 pt-10 md:-mx-8 md:px-8 md:pt-16"
      >
        <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/70 bg-white/75 px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.24em] text-cyan-700 shadow-sm backdrop-blur dark:border-cyan-500/20 dark:bg-slate-950/60 dark:text-cyan-300">
              <BadgeCheck className="h-3.5 w-3.5" />
              Multi-agent document extraction
            </div>

            <h1 className="mt-6 text-5xl font-semibold tracking-[-0.07em] text-slate-950 dark:text-white md:text-7xl md:leading-[0.94]">
              Upload a document.
              <span className="block text-slate-500 dark:text-slate-400">
                Leave with structured data.
              </span>
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600 dark:text-slate-300 md:text-xl">
              DocFlow turns invoices and contracts into review-ready structured output.
              Parser, extractor, and validator agents do the heavy lift, while low-confidence
              fields pause for human approval before export.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="#upload"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-slate-950 px-6 py-3 text-sm font-medium text-white transition-transform hover:-translate-y-0.5 dark:bg-white dark:text-slate-950"
              >
                Start with an upload
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="#how-it-works"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-300 bg-white/70 px-6 py-3 text-sm font-medium text-slate-800 backdrop-blur transition-colors hover:border-cyan-400 hover:text-cyan-700 dark:border-slate-700 dark:bg-slate-950/50 dark:text-slate-100 dark:hover:border-cyan-500 dark:hover:text-cyan-300"
              >
                Explore the pipeline
              </Link>
            </div>

            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              {stats.map((s) => (
                <SurfaceCard key={s.label} className="p-5">
                  <div
                    className="text-3xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-white"
                    style={{ fontFamily: 'var(--font-geist-mono)' }}
                  >
                    {s.value}
                  </div>
                  <div className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                    {s.label}
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                    {s.detail}
                  </div>
                </SurfaceCard>
              ))}
            </div>

            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {signals.map(({ title, desc, icon: Icon }) => (
                <div
                  key={title}
                  className="rounded-3xl border border-slate-200/70 bg-white/55 p-5 backdrop-blur-sm dark:border-white/10 dark:bg-slate-950/45"
                >
                  <Icon className="h-5 w-5 text-cyan-600 dark:text-cyan-300" />
                  <h2 className="mt-4 text-sm font-semibold text-slate-900 dark:text-white">
                    {title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {desc}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <SurfaceCard
            id="upload"
            className="relative overflow-hidden p-2 shadow-[0_40px_120px_-44px_rgba(14,116,144,0.6)]"
          >
            <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />
            <div className="rounded-[24px] border border-slate-200/70 bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),_transparent_46%),linear-gradient(180deg,_rgba(255,255,255,0.96),_rgba(240,249,255,0.88))] p-6 dark:border-white/10 dark:bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.14),_transparent_44%),linear-gradient(180deg,_rgba(15,23,42,0.9),_rgba(2,6,23,0.95))]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 pb-5 dark:border-white/10">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-3 w-3">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70 opacity-75" />
                      <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500 shadow-[0_0_18px_rgba(16,185,129,0.8)]" />
                    </span>
                    <p className="text-xs uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
                      Live intake
                    </p>
                  </div>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-white">
                    Drop a document into the pipeline
                  </h2>
                </div>
                <div className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-500/10 dark:text-cyan-300">
                  Invoices + contracts
                </div>
              </div>

              <div className="mt-6">
                <DocumentUploader variant="embedded" />
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                {[
                  'Agent pipeline routes the document automatically',
                  'Human review only appears where confidence drops',
                  'Exports stay ready for JSON, CSV, or webhook delivery',
                ].map((item) => (
                  <div
                    key={item}
                    className="rounded-2xl border border-slate-200/70 bg-white/70 px-4 py-3 text-sm leading-6 text-slate-600 dark:border-white/10 dark:bg-slate-900/60 dark:text-slate-300"
                  >
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </SurfaceCard>
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-6xl">
        <SectionHeading
          eyebrow="How it works"
          title="From raw PDF to structured data in four steps."
          description="Upload a document, let three agents handle parsing, extraction, and validation, then review any flagged fields and export clean results."
        />

        <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {steps.map((item) => (
            <ProcessStep
              key={item.label}
              icon={item.icon}
              step={item.step}
              title={item.label}
              description={item.desc}
            />
          ))}
        </div>
      </section>

      <section id="capabilities" className="mx-auto max-w-6xl">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <SectionHeading
            eyebrow="Why this feels serious"
            title="Every claim is anchored to a real operating model."
            description="The strongest product pages do not hide behind abstract AI language. They explain the mechanism, show where humans stay in control, and make the export path explicit."
          />

          <div className="grid gap-5 md:grid-cols-2">
            {capabilities.map(({ title, desc, icon: Icon, accent, className }) => (
              <SurfaceCard
                key={title}
                className={[
                  'relative overflow-hidden p-6',
                  className ?? '',
                ].join(' ')}
              >
                <div
                  className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accent}`}
                />
                <div className="relative">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-8 text-2xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white">
                    {title}
                  </h3>
                  <p className="mt-3 max-w-sm text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {desc}
                  </p>
                </div>
              </SurfaceCard>
            ))}
          </div>
        </div>
      </section>

      <section id="proof" className="mx-auto max-w-6xl">
        <SectionHeading
          eyebrow="Operational proof"
          title="Built for real document workflows, not just a good screenshot."
          description="The landing page should communicate measurable extraction quality, privacy posture, deployment flexibility, and the extension story for future document types."
          align="center"
        />

        <div className="mt-12 grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <SurfaceCard className="p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
              Benchmarks
            </p>
            <div className="mt-8 grid gap-6 sm:grid-cols-2">
              {stats.map((s) => (
                <div key={s.label}>
                  <div
                    className="text-5xl font-semibold tracking-[-0.06em] text-slate-950 dark:text-white"
                    style={{ fontFamily: 'var(--font-geist-mono)' }}
                  >
                    {s.value}
                  </div>
                  <div className="mt-2 text-base font-medium text-slate-900 dark:text-slate-100">
                    {s.label}
                  </div>
                  <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    {s.detail}
                  </div>
                </div>
              ))}
            </div>
          </SurfaceCard>

          <div className="grid gap-5">
            <SurfaceCard className="p-7">
              <div className="flex items-center gap-3">
                <ShieldCheck className="h-5 w-5 text-cyan-600 dark:text-cyan-300" />
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white">
                  Privacy posture
                </h3>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Documents are processed in-memory, with an option to switch providers or run locally
                for tighter control over where data moves.
              </p>
            </SurfaceCard>

            <SurfaceCard className="p-7">
              <div className="flex items-center gap-3">
                <Download className="h-5 w-5 text-cyan-600 dark:text-cyan-300" />
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white">
                  Extension path
                </h3>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                The plugin architecture matters for the homepage too. New document types should feel
                like an obvious next step, not a rewrite.
              </p>
            </SurfaceCard>
          </div>
        </div>
      </section>

      <section id="contact" className="mx-auto max-w-6xl">
        <SectionHeading
          eyebrow="Work with me"
          title="Three ways to take this further."
          description="Custom document pipelines, new document type plugins, or just a conversation about what you're building."
          align="center"
        />

        <div className="mt-12 grid gap-5 lg:grid-cols-3">
          {finalActions.map((item) => (
            <ActionCard
              key={item.title}
              icon={item.icon}
              title={item.title}
              description={item.desc}
              href={item.href}
              cta={item.cta}
              note={item.note}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
