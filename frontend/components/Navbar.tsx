'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useTheme } from 'next-themes';
import { Button } from 'antd';
import { Sun, Moon, FileText } from 'lucide-react';
import { TourTrigger } from '@/components/AppTour';
import { UsageBanner } from '@/components/SettingsModal';

export function Navbar() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link
            href="/"
            data-tour="logo"
            className="flex items-center gap-2 font-bold text-xl text-indigo-600 dark:text-indigo-400"
          >
            <FileText className="w-6 h-6" />
            <span>DocFlow</span>
          </Link>
          <nav className="hidden md:flex items-center gap-4 text-sm font-medium text-gray-600 dark:text-gray-300">
            <Link
              href="/#upload"
              data-tour="nav-upload"
              className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            >
              Upload
            </Link>
            <Link
              href="/#how-it-works"
              className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            >
              How it works
            </Link>
            <Link
              href="/#capabilities"
              className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            >
              Capabilities
            </Link>
            <Link
              href="/documents"
              data-tour="nav-documents"
              className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            >
              Documents
            </Link>
            <Link
              href="/#contact"
              className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            >
              Contact
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          {mounted && <TourTrigger />}
          {mounted && <UsageBanner />}
          {mounted && (
            <Button
              data-tour="theme-toggle"
              type="text"
              title={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              icon={
                resolvedTheme === 'dark'
                  ? <Sun className="w-5 h-5 text-yellow-400" />
                  : <Moon className="w-5 h-5 text-slate-600" />
              }
              onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
            />
          )}
        </div>
      </div>
    </header>
  );
}
