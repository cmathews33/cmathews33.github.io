import { Component, ChangeDetectionStrategy, signal, computed, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HistoryService, HistoryPeriod } from '../../services/history.service';
import { TickerHistory } from '../../services/api.service';

type SortOption = 'mentions' | 'change';

interface HistoryRow {
  ticker: string;
  periodPostCount: number;
  periodPriceChange: number | null;
  lastPrice: number | null;
  lastDate: string;
}

function toRow(th: TickerHistory): HistoryRow {
  const last = th.points[th.points.length - 1];
  return {
    ticker: th.ticker,
    periodPostCount: th.periodPostCount,
    periodPriceChange: th.periodPriceChange,
    lastPrice: last?.eodPrice ?? last?.price ?? null,
    lastDate: last?.date ?? '',
  };
}

@Component({
  selector: 'app-history',
  template: `
    <div class="page-header">
      <div class="page-header-inner">
        <div>
          <h1 class="page-title">Historical Trends</h1>
          <p class="page-sub">Reddit trending stocks with historical price performance</p>
        </div>
        @if (state().refreshedAt; as t) {
          <span class="stamp">Refreshed {{ t | date:'shortTime' }}</span>
        }
      </div>

      <div class="period-tabs" role="tablist" aria-label="Time period">
        @for (tab of periods; track tab.value) {
          <button
            role="tab"
            [attr.aria-selected]="period() === tab.value"
            [class.active]="period() === tab.value"
            class="period-tab"
            (click)="period.set(tab.value)"
          >{{ tab.label }}</button>
        }
      </div>
    </div>

    @if (state().loading) {
      <div class="loading-state" role="status" aria-live="polite">
        <div class="spinner" aria-hidden="true"></div>
        <p>Loading trending data&hellip;</p>
      </div>
    } @else if (state().error) {
      <div class="error-state" role="alert">
        <p>{{ state().error }}</p>
      </div>
    } @else if (state().data.length === 0) {
      <div class="loading-state" role="status" aria-live="polite">
        <div class="spinner" aria-hidden="true"></div>
        <p>Fetching trending data&hellip;</p>
      </div>
    } @else {
      <div class="list-wrapper">
        <div class="toolbar">
          <div class="search-wrapper">
            <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" />
            </svg>
            <input
              type="search"
              [ngModel]="searchQuery()"
              (ngModelChange)="searchQuery.set($event)"
              placeholder="Search tickers..."
              aria-label="Search stocks by ticker"
              class="search-input"
            />
          </div>
          <div class="sort-wrapper">
            <label for="hist-sort" class="sort-label">Sort</label>
            <select
              id="hist-sort"
              [ngModel]="sortBy()"
              (ngModelChange)="sortBy.set($event)"
              class="sort-select"
            >
              <option value="mentions">Most Mentioned</option>
              <option value="change">Top Gainers</option>
            </select>
          </div>
          <button class="btn-download" (click)="downloadCsv()" aria-label="Download current view as CSV">
            <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
            Download CSV
          </button>
        </div>

        <div class="table-wrapper" role="region" aria-label="Historical stocks data">
          <table class="stock-table">
            <thead>
              <tr>
                <th scope="col" class="col-rank">#</th>
                <th scope="col" class="col-ticker">Ticker</th>
                <th scope="col" class="col-price">Last Price</th>
                <th scope="col" class="col-change">{{ changeLabel() }}</th>
                <th scope="col" class="col-mentions">Reddit Posts</th>
                <th scope="col" class="col-time">Last Seen</th>
              </tr>
            </thead>
            <tbody>
              @if (filteredRows().length > 0) {
                @for (row of filteredRows(); track row.ticker; let i = $index) {
                  <tr class="stock-row">
                    <td class="col-rank rank-num">{{ i + 1 }}</td>
                    <td class="col-ticker">
                      <span class="ticker-sym">{{ row.ticker }}</span>
                    </td>
                    <td class="col-price price-val">
                      @if (row.lastPrice != null && row.lastPrice > 0) {
                        &#36;{{ row.lastPrice | number:'1.2-2' }}
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td
                      class="col-change change-val"
                      [class.positive]="(row.periodPriceChange ?? 0) > 0"
                      [class.negative]="(row.periodPriceChange ?? 0) < 0"
                    >
                      @if (row.periodPriceChange != null) {
                        {{ row.periodPriceChange >= 0 ? '+' : '' }}{{ row.periodPriceChange | number:'1.2-2' }}%
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td class="col-mentions mentions-val">{{ row.periodPostCount | number }}</td>
                    <td class="col-time time-val">{{ row.lastDate }}</td>
                  </tr>
                }
              } @else {
                <tr>
                  <td colspan="6" class="no-results">No stocks match your search.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <p class="results-count">
          Showing {{ filteredRows().length }} of {{ state().data.length }} stocks
          &bull; Refreshes every 24 hours
        </p>
      </div>
    }
  `,
  styleUrls: ['./history.component.css'],
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HistoryComponent {
  private readonly histService = inject(HistoryService);

  readonly period      = signal<HistoryPeriod>('month');
  readonly searchQuery = signal('');
  readonly sortBy      = signal<SortOption>('mentions');

  readonly periods: { value: HistoryPeriod; label: string }[] = [
    { value: 'day',   label: 'Day' },
    { value: 'week',  label: 'Week' },
    { value: 'month', label: 'Month' },
    { value: 'year',  label: 'Year' },
  ];

  readonly changeLabel = computed(() => ({
    day:   "Today's change",
    week:  "This week's change",
    month: "This month's change",
    year:  "This year's change",
  }[this.period()]));

  readonly state = computed(() => this.histService.getState(this.period())());

  readonly filteredRows = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const sort  = this.sortBy();
    let rows = this.state().data.map(toRow);

    if (query) {
      rows = rows.filter(r => r.ticker.toLowerCase().includes(query));
    }

    return [...rows].sort((a, b) => {
      if (sort === 'change') {
        return (b.periodPriceChange ?? -Infinity) - (a.periodPriceChange ?? -Infinity);
      }
      return b.periodPostCount - a.periodPostCount;
    });
  });

  constructor() {
    effect(() => { this.histService.load(this.period()); });
  }

  downloadCsv(): void {
    const rows   = this.filteredRows();
    const period = this.period();
    const header = 'Rank,Ticker,Last Price,Period Change (%),Reddit Posts,Last Seen';
    const lines  = rows.map((r, i) =>
      [
        i + 1,
        r.ticker,
        r.lastPrice != null ? r.lastPrice.toFixed(2) : '',
        r.periodPriceChange != null ? r.periodPriceChange.toFixed(2) : '',
        r.periodPostCount,
        r.lastDate,
      ].join(',')
    );
    const csv  = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `harrys-risers-${period}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
