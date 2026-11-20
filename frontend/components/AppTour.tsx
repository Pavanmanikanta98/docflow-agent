'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { TourProvider, useTour } from '@reactour/tour';
import { Button } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import { useHydrated } from '@/lib/useHydrated';
import { pageKeyFor, resolveSteps } from '@/lib/tour';

const PHONE_MAX_WIDTH = 640;
const POPOVER_MAX_WIDTH = 340;
const POPOVER_HEIGHT_ESTIMATE = 230;
const POPOVER_GAP = 16;

// On a phone the popover is centred across the screen, directly below the
// highlighted target (or above it when there is no room below), so it can
// never run past an edge. On wider screens the library places it itself.
function phonePosition(target: {
  windowWidth: number;
  windowHeight: number;
  top: number;
  height: number;
}): [number, number] {
  const width = Math.min(target.windowWidth * 0.92, POPOVER_MAX_WIDTH);
  const x = (target.windowWidth - width) / 2;
  const below = target.top + target.height + POPOVER_GAP;
  const y =
    below + POPOVER_HEIGHT_ESTIMATE <= target.windowHeight
      ? below
      : Math.max(8, target.top - POPOVER_HEIGHT_ESTIMATE - POPOVER_GAP);
  return [x, y];
}

function StepContent({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <strong className="block text-base mb-1">{title}</strong>
      <p className="text-sm text-gray-600 dark:text-gray-400">{body}</p>
    </div>
  );
}

// Starts the tour for the page the visitor is on. The steps are worked out
// when the button is pressed, so only targets that are on screen are used.
function TourTrigger() {
  const { setIsOpen, setCurrentStep, setSteps } = useTour();
  const pathname = usePathname();

  return (
    <Button
      type="primary"
      ghost
      size="small"
      icon={<PlayCircleOutlined />}
      aria-label="Start tour"
      onClick={() => {
        const steps = resolveSteps(pageKeyFor(pathname));
        if (steps.length === 0) return;
        const onPhone = window.innerWidth < PHONE_MAX_WIDTH;
        setSteps?.(
          steps.map((step) => ({
            selector: step.element,
            ...(onPhone ? { position: phonePosition } : {}),
            content: <StepContent title={step.title} body={step.body} />,
            // A target inside a scrolling panel (the review card) is brought
            // into view before it is highlighted.
            action: (element) => element?.scrollIntoView({ block: 'center' }),
          })),
        );
        setCurrentStep(0);
        setIsOpen(true);
      }}
    >
      {/* Icon only on phones: the label pushed the theme toggle off screen. */}
      <span className="hidden sm:inline">Start Tour</span>
    </Button>
  );
}

export function AppTour({ children }: { children: React.ReactNode }) {
  const hydrated = useHydrated();

  if (!hydrated) return <>{children}</>;

  return (
    <TourProvider
      steps={[]}
      styles={{
        popover: (base) => ({
          ...base,
          borderRadius: 12,
          padding: '20px 24px',
          maxWidth: `min(92vw, ${POPOVER_MAX_WIDTH}px)`,
        }),
        badge: (base) => ({
          ...base,
          background: '#d97706',
        }),
        dot: (base, state) => ({
          ...base,
          background: state?.current ? '#d97706' : '#d1d5db',
        }),
      }}
      padding={{ mask: 8, popover: [8, 10] }}
    >
      {children}
    </TourProvider>
  );
}

export { TourTrigger };
