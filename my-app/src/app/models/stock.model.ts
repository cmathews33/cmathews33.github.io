export interface RedditPostLink {
  title: string;
  url: string;
  subreddit: string;
  postedAt: string; // ISO 8601
}

export interface Stock {
  ticker: string;
  name: string;
  price: number;
  priceChange: number;
  percentChange: number;
  mentionScore: number;
  totalComments: number;
  source: string;
  postTimestamp: Date;
  posts: RedditPostLink[];
  sodPrice: number | null;
}

export interface StocksResponse {
  stocks: Stock[];
  refreshedAt: string;
}

export type HistoryPeriod = 'day' | 'week' | 'month' | 'year';

export interface HistoryPoint {
  date: string;
  sodPrice: number | null;
  eodPrice: number | null;
  price: number | null;         // legacy alias for eodPrice
  priceChange: number | null;
  percentChange: number | null;
  postCount: number;
  mentionCount: number;         // legacy alias for postCount
  posts: RedditPostLink[];
  source: string;
}

export interface TickerHistory {
  ticker: string;
  periodPostCount: number;
  periodPriceChange: number | null;
  points: HistoryPoint[];
}
