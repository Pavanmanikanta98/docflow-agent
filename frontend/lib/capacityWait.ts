/** ADR 006 — format a document's capacity-wait state for display. */

export function formatCapacityWaitMessage(estimatedStartIso: string | null): string {
  if (!estimatedStartIso) return 'Waiting for capacity';
  const start = new Date(estimatedStartIso);
  if (Number.isNaN(start.getTime())) return 'Waiting for capacity';
  const hh = String(start.getHours()).padStart(2, '0');
  const mm = String(start.getMinutes()).padStart(2, '0');
  return `Waiting for capacity — starts ~${hh}:${mm}`;
}
