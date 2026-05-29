export interface Stock {
  ticker: string;
  name: string;
  price: number;
  priceChange: number;
  percentChange: number;
  commentCount: number;
  sentiment: 'positive' | 'neutral' | 'negative';
  source: string;
  timestamp: Date;
}
