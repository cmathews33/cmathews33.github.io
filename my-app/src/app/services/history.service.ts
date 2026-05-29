import { Injectable, inject, signal, WritableSignal, Signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Stock } from '../models/stock.model';
import { ApiService, HistoryPeriod } from './api.service';

export type { HistoryPeriod };

export interface PeriodState {
  readonly stocks: Stock[];
  readonly loading: boolean;
  readonly error: string | null;
  readonly refreshedAt: Date | null;
}

const INITIAL_STATE: PeriodState = { stocks: [], loading: false, error: null, refreshedAt: null };

// Thin client: the backend computes period price change from real history.
// Per-period state + the load()/getState() API are unchanged so HistoryComponent
// is untouched.
@Injectable({ providedIn: 'root' })
export class HistoryService {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly _states: Record<HistoryPeriod, WritableSignal<PeriodState>> = {
    '1mo': signal<PeriodState>(INITIAL_STATE),
    '6mo': signal<PeriodState>(INITIAL_STATE),
    '1yr': signal<PeriodState>(INITIAL_STATE),
  };

  getState(period: HistoryPeriod): Signal<PeriodState> {
    return this._states[period].asReadonly();
  }

  load(period: HistoryPeriod): void {
    const s = this._states[period];
    if (s().loading || s().stocks.length > 0) return;

    s.update(st => ({ ...st, loading: true, error: null }));
    this.api.getHistorical(period)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: stocks => s.set({ stocks, loading: false, error: null, refreshedAt: new Date() }),
        error: () =>
          s.update(st => ({ ...st, loading: false, error: 'Failed to load historical data. Try again later.' })),
      });
  }
}
