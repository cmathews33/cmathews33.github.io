export interface Stock {
  ticker: string;
  name: string;
  price: number;
  priceChange: number;
  percentChange: number;
  mentionScore: number;
  source: string;
  postTimestamp: Date;
}
