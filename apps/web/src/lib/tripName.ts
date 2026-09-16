export function shouldPersistTripName(draft: string, saved: string): boolean {
  const next = draft.trim();
  return next.length > 0 && next !== saved;
}
