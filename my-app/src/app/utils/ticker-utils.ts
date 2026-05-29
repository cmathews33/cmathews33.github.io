// Display helper only. Ticker extraction/scoring now lives in the Python backend
// (backend/app/services/ticker_utils.py).

// Returns a display label for a source value.
// Reddit subreddits get an r/ prefix; StockTwits gets its own brand label.
export function formatSource(source: string): string {
  if (source === 'stocktwits') return 'StockTwits';
  if (source === 'wallstreetbets') return 'r/wsb';
  return `r/${source}`;
}
