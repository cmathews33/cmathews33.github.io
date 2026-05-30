export function formatSource(source: string): string {
  if (source === 'wallstreetbets') return 'r/wsb';
  return `r/${source}`;
}
