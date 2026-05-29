import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { Stock } from '../models/stock.model';
import { environment } from '../../environments/environment';

// Wire-format of a Stock as returned by the Flask API (timestamp is an ISO string).
interface StockDto extends Omit<Stock, 'timestamp'> {
  timestamp: string;
}

export type HistoryPeriod = '1mo' | '6mo' | '1yr';

// Single gateway to the backend. All Reddit/StockTwits/price work happens
// server-side now; the frontend just reads JSON.
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  getStocks(): Observable<Stock[]> {
    return this.http
      .get<StockDto[]>(`${this.base}/api/stocks`)
      .pipe(map(dtos => dtos.map(this.toStock)));
  }

  getHistorical(period: HistoryPeriod): Observable<Stock[]> {
    return this.http
      .get<StockDto[]>(`${this.base}/api/historical?period=${period}`)
      .pipe(map(dtos => dtos.map(this.toStock)));
  }

  private toStock(dto: StockDto): Stock {
    return { ...dto, timestamp: new Date(dto.timestamp) };
  }
}
