import { useSyncExternalStore } from 'react';

const subscribe = () => () => {};

/**
 * True once React has hydrated on the client, false during SSR and the
 * hydration render. Lets a component render client-only UI (theme-aware
 * widgets, DOM-bound providers) without a `setState` inside `useEffect`.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
