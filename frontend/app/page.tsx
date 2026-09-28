import Link from 'next/link';
import DocumentUploader from '@/components/DocumentUploader';
import { ProcessStep } from '@/components/landing/ProcessStep';
import { SectionHeading } from '@/components/landing/SectionHeading';
import { SurfaceCard } from '@/components/landing/SurfaceCard';
import {
  Bot,
  Cable,
  CheckCircle2,
  Cpu,
  Download,
  FileText,
  Code2,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface Step {
  icon: LucideIcon;
  step: string;
  label: string;
  desc: string;
}

interface Capability {
  title: string;
  desc: string;
  icon: LucideIcon;
  accent: string;
  className?: string;
}

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
const GITHUB_URL =
  process.env.NEXT_PUBLIC_GITHUB_URL ?? 'https://github.com/Pavanmanikanta98/docflow-agent';

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
        className="relative -mx-4 overflow-hidden px-4 pt-14 md:-mx-8 md:px-8 md:pt-20"
      >
        <div className="mx-auto max-w-4xl text-center">
          <div className="inline-flex items-center gap-2 border-l-2 border-amber-500 pl-3 text-left text-xs font-medium uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
            Free to try, right now · no signup · real Groq API underneath
          </div>

          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-white md:text-6xl md:leading-[1.02]">
            Messy PDF in. Clean data out.
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-600 dark:text-slate-300">
            This is the same pipeline I&apos;d build for your documents — try it below, then{' '}
            <Link href="#contact" className="font-medium !text-slate-800 !underline decoration-amber-400 decoration-2 underline-offset-4 hover:!text-amber-600 dark:!text-slate-100 dark:decoration-amber-500">
              tell me what&apos;s different about yours
            </Link>
            .
          </p>
        </div>

        <SurfaceCard
          id="upload"
          className="relative mx-auto mt-12 max-w-5xl overflow-hidden p-2 shadow-[0_50px_140px_-40px_rgba(14,116,144,0.55)]"
        >
          <div className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-400/70 to-transparent" />
          <div className="rounded-[24px] border border-slate-200/70 bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.1),_transparent_46%),linear-gradient(180deg,_rgba(255,255,255,0.97),_rgba(248,250,252,0.9))] p-6 dark:border-white/10 dark:bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.12),_transparent_44%),linear-gradient(180deg,_rgba(15,23,42,0.92),_rgba(2,6,23,0.96))] md:p-8">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 pb-5 dark:border-white/10">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_18px_rgba(16,185,129,0.8)]" />
                </span>
                <p className="text-xs uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
                  Live — invoices + contracts
                </p>
              </div>
              <Link
                href="#how-it-works"
                className="text-xs font-medium !text-slate-500 !underline decoration-slate-300 underline-offset-2 hover:!text-amber-600 dark:!text-slate-400 dark:decoration-slate-600"
              >
                See how it works under the hood →
              </Link>
            </div>

            <div className="mt-6">
              <DocumentUploader variant="embedded" />
            </div>
          </div>
        </SurfaceCard>

        <div className="mx-auto mt-8 flex max-w-5xl flex-wrap items-center justify-center gap-x-8 gap-y-3 text-center text-sm text-slate-500 dark:text-slate-400">
          <span><strong className="font-semibold text-slate-900 dark:text-white">96.7%</strong> field accuracy, real test set</span>
          <span className="hidden text-slate-300 dark:text-slate-700 sm:inline">·</span>
          <span><strong className="font-semibold text-slate-900 dark:text-white">0</strong> failures across 230 live API calls</span>
          <span className="hidden text-slate-300 dark:text-slate-700 sm:inline">·</span>
          <span>every number above links to a <Link href="#proof" className="font-medium !text-slate-700 !underline decoration-slate-300 underline-offset-2 hover:!text-amber-600 dark:!text-slate-300 dark:decoration-slate-600">committed results file</Link></span>
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
            eyebrow="Architecture"
            title="Built like production, not a weekend demo."
            description="A queue instead of inline processing. A second LLM call to grade the first. A calibrated judge instead of a self-graded score. These are the decisions that separate a working pipeline from a prompt in a loop."
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
          eyebrow="Measured, not marketed"
          title="Every figure below comes from a committed results file."
          description="No case study copy. The evaluation harness, the golden dataset, and the raw run logs all live in this repository — click through and check the math yourself."
          align="center"
        />

        <div className="mt-12 grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <SurfaceCard className="p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
              Live evaluation results
            </p>
            <div className="mt-8 grid gap-6 sm:grid-cols-2">
              {[
                { value: '96.7%', label: 'Structured field accuracy', detail: 'gpt-oss-120b, 32-case golden set' },
                { value: '86.25%', label: 'OCR text-layer baseline', detail: '20-case synthetic evaluation' },
                { value: '0.993', label: 'Calibrated judge score', detail: 'termination_clause, GEval vs 35.7% fuzzy' },
                { value: '8000 TPM', label: 'Free-tier ceiling, handled', detail: 'Redis token budget, defers not fails' },
              ].map((s) => (
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
                  Honest about what&apos;s not measured
                </h3>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Cost-per-document isn&apos;t reported here because no run has captured per-case
                token usage yet. A confident-sounding number with nothing behind it is worse
                than admitting the gap.
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
                New document types are a plugin — one file implementing a shared interface,
                not a rewrite of the pipeline that already works.
              </p>
            </SurfaceCard>
          </div>
        </div>
      </section>

      <section id="about" className="mx-auto max-w-6xl">
        <SurfaceCard className="relative overflow-hidden p-8 md:p-12">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-fuchsia-500/10" />
          <div className="relative grid gap-8 md:grid-cols-[auto_1fr] md:items-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">
              <Sparkles className="h-7 w-7" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-cyan-600 dark:text-cyan-300">
                Who built this
              </p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white md:text-3xl">
                Pavan — this is a working system, built and measured end to end.
              </h2>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
                Every layer here — the queue, the confidence gate, the rate-limit handling,
                the calibrated LLM judge — was a deliberate call, written up in this
                repository&apos;s architecture decisions rather than left implicit. If you&apos;re
                hiring or have a document pipeline that needs the same rigor, I&apos;d like to
                talk.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  href={GITHUB_URL}
                  className="inline-flex items-center gap-2 rounded-full !bg-slate-950 px-5 py-2.5 text-sm font-medium !text-white transition-transform hover:-translate-y-0.5 dark:!bg-white dark:!text-slate-950"
                >
                  <Code2 className="h-4 w-4" />
                  View the repository
                </Link>
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-300 !bg-white/70 px-5 py-2.5 text-sm font-medium !text-slate-800 backdrop-blur transition-colors hover:border-amber-400 hover:!text-amber-700 dark:border-slate-700 dark:!bg-slate-950/50 dark:!text-slate-100 dark:hover:border-amber-500 dark:hover:!text-amber-300"
                >
                  Get in touch
                </a>
              </div>
            </div>
          </div>
        </SurfaceCard>
      </section>

      <section id="contact" className="mx-auto max-w-2xl">
        <div className="border-t border-slate-200 pt-16 dark:border-white/10">
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
            Get in touch
          </p>
          <h2 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white md:text-4xl">
            Have documents that don&apos;t look like these?
          </h2>

          <div className="mt-8 space-y-5 text-lg leading-8 text-slate-600 dark:text-slate-300">
            <p>
              I&apos;m Pavan. I built this pipeline myself — parsing, extraction,
              validation, the review queue, all of it. If you&apos;ve got invoices,
              contracts, or something else that needs the same treatment, tell me
              what&apos;s different about yours and I&apos;ll tell you honestly
              whether it&apos;s a good fit.
            </p>
            <p>No forms, no sales call. Just write to me directly:</p>
          </div>

          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="mt-6 inline-block text-2xl font-medium !text-slate-950 !underline decoration-amber-400 decoration-2 underline-offset-4 hover:!text-amber-700 dark:!text-white dark:hover:!text-amber-300"
          >
            {CONTACT_EMAIL.split(',')[0]}
          </a>

          <p className="mt-10 text-sm text-slate-500 dark:text-slate-400">
            Prefer to read the code first?{' '}
            <a
              href={GITHUB_URL}
              className="font-medium !text-slate-700 !underline decoration-slate-300 underline-offset-2 hover:!text-amber-600 dark:!text-slate-300 dark:decoration-slate-600"
            >
              Here&apos;s the source and every architecture decision behind it
            </a>
            .
          </p>

          <p className="mt-16 font-serif text-xl italic text-slate-400 dark:text-slate-500">
            — Pavan
          </p>
        </div>
      </section>
    </div>
  );
}
