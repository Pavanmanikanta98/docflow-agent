'use client';

import React from 'react';
import { ConfigProvider, theme, App } from 'antd';
import { ThemeProvider as NextThemesProvider, useTheme } from 'next-themes';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { useHydrated } from '@/lib/useHydrated';

function AntdThemeProvider({ children }: { children: React.ReactNode }) {
  const { resolvedTheme } = useTheme();
  const hydrated = useHydrated();

  if (!hydrated) {
    return <div style={{ visibility: 'hidden' }}>{children}</div>;
  }

  return (
    <ConfigProvider
      theme={{
        algorithm:
          resolvedTheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#6366f1',
          borderRadius: 8,
          fontFamily: 'inherit',
        },
      }}
    >
      <App>{children}</App>
    </ConfigProvider>
  );
}

export function ThemeRegistry({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem>
      <AntdRegistry>
        <AntdThemeProvider>{children}</AntdThemeProvider>
      </AntdRegistry>
    </NextThemesProvider>
  );
}
