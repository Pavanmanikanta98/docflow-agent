'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useTheme } from 'next-themes';
import { Button, Drawer } from 'antd';
import { Sun, Moon, FileText, Code2, Menu } from 'lucide-react';
import { TourTrigger } from '@/components/AppTour';
import { UsageBanner } from '@/components/SettingsModal';

const GITHUB_URL =
  process.env.NEXT_PUBLIC_GITHUB_URL ?? 'https://github.com/Pavanmanikanta98/docflow-agent';

const navLinks = [
  { href: '/#upload', label: 'Upload', tour: 'nav-upload' },
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/#capabilities', label: 'Capabilities' },
  { href: '/documents', label: 'Documents', tour: 'nav-documents' },
  { href: '/#contact', label: 'Contact' },
];

export function Navbar() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200/70 bg-white/85 backdrop-blur-md dark:border-white/10 dark:bg-slate-950/85">
      <div className="container mx-auto flex h-[72px] items-center justify-between gap-2 px-4">
        <div className="flex items-center gap-8">
          <Link
            href="/"
            data-tour="logo"
            className="group flex items-center gap-2.5"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-950 text-white dark:bg-white dark:text-slate-950">
              <FileText className="h-4 w-4" />
            </span>
            <span className="hidden text-[1.05rem] font-semibold tracking-[-0.02em] text-slate-950 dark:text-white min-[400px]:inline">
              DocFlow
            </span>
          </Link>
          <nav className="hidden items-center gap-7 text-sm font-medium text-slate-500 dark:text-slate-400 lg:flex">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                data-tour={link.tour}
                className="relative py-1 !text-slate-500 transition-colors hover:!text-slate-950 dark:!text-slate-400 dark:hover:!text-white after:absolute after:inset-x-0 after:-bottom-[26px] after:h-[2px] after:origin-left after:scale-x-0 after:bg-amber-500 after:transition-transform hover:after:scale-x-100"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-1.5">
          <Link
            href={GITHUB_URL}
            className="hidden items-center gap-1.5 rounded-full border border-slate-200 px-3.5 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-950 dark:border-white/10 dark:text-slate-300 dark:hover:border-white/20 dark:hover:text-white sm:inline-flex"
          >
            <Code2 className="h-3.5 w-3.5" />
            Source
          </Link>
          {mounted && <TourTrigger />}
          {mounted && <UsageBanner />}
          {mounted && (
            <Button
              className="lg:!hidden"
              type="text"
              shape="circle"
              aria-label="Open menu"
              data-testid="menu-button"
              icon={<Menu className="h-4 w-4 text-slate-600 dark:text-slate-300" />}
              onClick={() => setMenuOpen(true)}
            />
          )}
          {mounted && (
            <Button
              data-tour="theme-toggle"
              type="text"
              shape="circle"
              title={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              icon={
                resolvedTheme === 'dark'
                  ? <Sun className="h-4 w-4 text-amber-400" />
                  : <Moon className="h-4 w-4 text-slate-500" />
              }
              onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
            />
          )}
        </div>
      </div>
      <Drawer
        title="DocFlow"
        placement="right"
        size="default"
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      >
        <nav className="flex flex-col gap-1" data-testid="menu-drawer">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="rounded-lg px-3 py-3 text-base font-medium !text-slate-700 hover:bg-slate-100 dark:!text-slate-200 dark:hover:bg-white/10"
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={GITHUB_URL}
            onClick={() => setMenuOpen(false)}
            className="mt-2 inline-flex items-center gap-2 rounded-lg px-3 py-3 text-base font-medium !text-slate-700 hover:bg-slate-100 dark:!text-slate-200 dark:hover:bg-white/10"
          >
            <Code2 className="h-4 w-4" />
            Source
          </Link>
        </nav>
      </Drawer>
    </header>
  );
}
