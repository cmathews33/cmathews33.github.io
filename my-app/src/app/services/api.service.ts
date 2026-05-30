import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { Stock } from '../models/stock.model';
import { environment } from '../../environments/environment';

interface StockDto extends Omit<Stock, 'postTimestamp'> {
  postTimestamp: string;
}

interface StocksResponse {
  stocks: StockDto[];
  refreshedAt: string;
}

export interface HistoricalPoint {
  date: string;
  price: number;
  mentionCount: number;
  source: string;
}

export interface TickerHistory {
  ticker: string;
  points: HistoricalPoint[];
}

export type HistoryPeriod = '1mo' | '6mo' | '1yr';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  getStocks(): Observable<{ stocks: Stock[]; refreshedAt: Date }> {
    return this.http
      .get<StocksResponse>(`${this.base}/api/stocks`)
      .pipe(
        map(r => ({
          stocks: r.stocks.map(this.toStock),
          refreshedAt: new Date(r.refreshedAt),
        }))
      );
  }

  getHistorical(period: HistoryPeriod): Observable<TickerHistory[]> {
    return this.http.get<TickerHistory[]>(
      `${this.base}/api/historical?period=${period}`
    );
  }

  private toStock(dto: StockDto): Stock {
    return { ...dto, postTimestamp: new Date(dto.postTimestamp) };
  }
}
