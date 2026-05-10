'use client';

import React, { useState, useEffect } from 'react';
import { TourProvider, useTour } from '@reactour/tour';
import { Button } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';

const steps = [
  {
    selector: '[data-tour="logo"]',
    content: (
      <div>
        <strong className="block text-base mb-1">Welcome to DocFlow 👋</strong>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          AI-powered document extraction. Upload an invoice or contract and let our agents extract structured data automatically.
        </p>
      </div>
    ),
  },
  {
    selector: '[data-tour="nav-upload"]',
    content: (
      <div>
        <strong className="block text-base mb-1">Step 1 — Upload</strong>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Start here. Drag and drop any PDF invoice or contract onto the upload zone.
        </p>
      </div>
    ),
  },
  {
    selector: '[data-tour="nav-documents"]',
    content: (
      <div>
        <strong className="block text-base mb-1">Step 2 — Documents</strong>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Track all uploaded documents here. The status auto-refreshes every 3 seconds so you can watch extraction happen in real time.
        </p>
      </div>
    ),
  },
  {
    selector: '[data-tour="theme-toggle"]',
    content: (
      <div>
        <strong className="block text-base mb-1">Light / Dark Mode</strong>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Toggle between light and dark themes instantly — your preference is saved.
        </p>
      </div>
    ),
  },
  {
    selector: '[data-tour="settings"]',
    content: (
      <div>
        <strong className="block text-base mb-1">Usage & API Key ⚡</strong>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Track your remaining free extractions here. You get 10 per day. Need more? Paste your own Groq API key for unlimited access.
        </p>
      </div>
    ),
  },
];

// Button that triggers the tour — rendered inside TourProvider context
function TourTrigger() {
  const { setIsOpen, setCurrentStep } = useTour();

  return (
    <Button
      type="primary"
      ghost
      size="small"
      icon={<PlayCircleOutlined />}
      onClick={() => {
        setCurrentStep(0);
        setIsOpen(true);
      }}
    >
      Start Tour
    </Button>
  );
}

export function AppTour({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <>{children}</>;

  return (
    <TourProvider
      steps={steps}
      styles={{
        popover: (base) => ({
          ...base,
          borderRadius: 12,
          padding: '20px 24px',
        }),
        badge: (base) => ({
          ...base,
          background: '#6366f1',
        }),
        dot: (base, state) => ({
          ...base,
          background: state?.current ? '#6366f1' : '#d1d5db',
        }),
      }}
      padding={{ mask: 8, popover: [8, 10] }}
    >
      {children}
    </TourProvider>
  );
}

export { TourTrigger };
