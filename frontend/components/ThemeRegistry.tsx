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
          colorPrimary: '#d97706',
          colorLink: '#d97706',
          colorLinkHover: '#b45309',
          colorLinkActive: '#92400e',
          borderRadius: 14,
          fontFamily: 'inherit',
          ...(resolvedTheme === 'dark'
            ? { colorBgContainer: '#0f172a', colorBgElevated: '#0f172a' }
            : {}),
        },
        components: {
          Button: { controlHeight: 40, fontWeight: 500 },
          Card: { borderRadiusLG: 20 },
          Table: { borderRadius: 16 },
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
