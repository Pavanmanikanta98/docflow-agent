import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { ThemeRegistry } from '@/components/ThemeRegistry';
import { Navbar } from '@/components/Navbar';

import { AppTour } from '@/components/AppTour';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'DocFlow | Document Data Extraction',
  description: 'AI-powered document extraction and review platform',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col bg-slate-50 dark:bg-gray-950 text-slate-900 dark:text-slate-50 transition-colors duration-200`}>
        <ThemeRegistry>
          <AppTour>

            <Navbar />
            <main className="flex-1 w-full max-w-7xl mx-auto p-4 md:p-8">
              {children}
            </main>
          </AppTour>
        </ThemeRegistry>
      </body>
    </html>
  );
}
