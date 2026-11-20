import tourData from './tour.json';

export type PageKey = 'home' | 'documents' | 'review';

interface TourStepDefinition {
  id: string;
  /** data-tour ids, in order of preference: the first one on screen wins. */
  targets: string[];
  title: string;
  body: string;
}

export interface ResolvedTourStep {
  id: string;
  title: string;
  body: string;
  element: Element;
}

const pages = tourData.pages as Record<PageKey, TourStepDefinition[]>;

/** Which tour applies to the page the visitor is on. */
export function pageKeyFor(pathname: string | null): PageKey {
  if (pathname?.startsWith('/review/')) return 'review';
  if (pathname === '/documents') return 'documents';
  return 'home';
}

function isOnScreen(element: Element): boolean {
  const rect = element.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return false;
  const style = getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden';
}

/**
 * The steps that can be shown right now. A step whose targets are all hidden
 * or missing (the desktop nav on a phone, the export panel of a document that
 * is not completed yet) is left out, so the tour never highlights nothing.
 */
export function resolveSteps(page: PageKey, root: Document = document): ResolvedTourStep[] {
  const steps: ResolvedTourStep[] = [];
  for (const step of pages[page]) {
    for (const id of step.targets) {
      const element = Array.from(root.querySelectorAll(`[data-tour="${id}"]`)).find(isOnScreen);
      if (element) {
        steps.push({ id: step.id, title: step.title, body: step.body, element });
        break;
      }
    }
  }
  return steps;
}
