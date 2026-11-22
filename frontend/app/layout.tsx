import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import { ThemeRegistry } from '@/components/ThemeRegistry';
import { Navbar } from '@/components/Navbar';

import { AppTour } from '@/components/AppTour';

// Fonts are files in this repo, not downloads. `next/font/google` fetched them
// from Google on every build, and one failed fetch failed the build (CI and
// Vercel). Same families, same Latin subset, same weights as before; Google
// serves one variable file per style and reuses it across weights.
const geistSans = localFont({
  variable: '--font-geist-sans',
  src: './font-geist.woff2',
  weight: '100 900',
  display: 'swap',
});

const geistMono = localFont({
  variable: '--font-geist-mono',
  src: './font-geist-mono.woff2',
  weight: '100 900',
  display: 'swap',
  adjustFontFallback: false,
});

const sourceSerif = localFont({
  variable: '--font-letter-serif',
  src: [
    { path: './font-source-serif-4.woff2', weight: '400', style: 'normal' },
    { path: './font-source-serif-4.woff2', weight: '600', style: 'normal' },
    { path: './font-source-serif-4-italic.woff2', weight: '400', style: 'italic' },
    { path: './font-source-serif-4-italic.woff2', weight: '600', style: 'italic' },
  ],
  display: 'swap',
  adjustFontFallback: 'Times New Roman',
});

const caveat = localFont({
  variable: '--font-signature',
  src: [
    { path: './font-caveat.woff2', weight: '500', style: 'normal' },
    { path: './font-caveat.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  adjustFontFallback: false,
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
      <body className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} ${caveat.variable} antialiased min-h-screen flex flex-col bg-slate-50 dark:bg-gray-950 text-slate-900 dark:text-slate-50 transition-colors duration-200`}>
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
