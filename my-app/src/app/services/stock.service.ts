import { Injectable, inject, signal, computed } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { Stock } from '../models/stock.model';
import { ApiService } from './api.service';

// The backend collects + prices data on a schedule; the frontend just polls the
// cached snapshot. Public signal API is unchanged so StockListComponent is untouched.
const POLL_MS = 15 * 60 * 1000;

@Injectable({ providedIn: 'root' })
export class StockService {
  private readonly api = inject(ApiService);

  private readonly _stocks    = signal<Stock[]>([]);
  private readonly _loading   = signal(true);
  private readonly _error     = signal<string | null>(null);
  private readonly _refreshed = signal<Date | null>(null);

  readonly stocksList      = this._stocks.asReadonly();
  readonly isLoading       = this._loading.asReadonly();
  readonly error           = this._error.asReadonly();
  // Both stamps reflect the same backend snapshot now (social + prices fetched together).
  readonly redditRefreshed = this._refreshed.asReadonly();
  readonly priceRefreshed  = this._refreshed.asReadonly();

  constructor() {
    timer(0, POLL_MS)
      .pipe(
        switchMap(() => this.api.getStocks()),
        takeUntilDestroyed()
      )
      .subscribe({
        next: ({ stocks, refreshedAt }) => {
          this._stocks.set(stocks);
          this._loading.set(false);
          this._error.set(null);
          this._refreshed.set(refreshedAt);
        },
        error: () => {
          this._loading.set(false);
          this._error.set('Failed to fetch data. Retrying in 15 minutes.');
        },
      });
  }
}
