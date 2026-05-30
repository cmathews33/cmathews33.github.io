import { Component, ChangeDetectionStrategy, signal, computed, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HistoryService, HistoryPeriod } from '../../services/history.service';
import { TickerHistory } from '../../services/api.service';

type SortOption = 'mentions' | 'change';

interface HistoryRow {
  ticker: string;
  lastPrice: number;
  priceChange: number;
  percentChange: number;
  mentionCount: number;
  lastDate: string;
}

function toRow(th: TickerHistory): HistoryRow {
  const pts = th.points;
  const last  = pts[pts.length - 1];
  const first = pts[0];
  const lastPrice   = last?.price ?? 0;
  const firstPrice  = first?.price ?? 0;
  const priceChange   = firstPrice > 0 ? lastPrice - firstPrice : 0;
  const percentChange = firstPrice > 0 ? (priceChange / firstPrice) * 100 : 0;
  return {
    ticker:       th.ticker,
    lastPrice,
    priceChange,
    percentChange,
    mentionCount: last?.mentionCount ?? 0,
    lastDate:     last?.date ?? '',
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
        </div>

        <div class="table-wrapper" role="region" aria-label="Historical stocks data">
          <table class="stock-table">
            <thead>
              <tr>
                <th scope="col" class="col-rank">#</th>
                <th scope="col" class="col-ticker">Ticker</th>
                <th scope="col" class="col-price">Last Price</th>
                <th scope="col" class="col-change">{{ changeLabel() }}</th>
                <th scope="col" class="col-mentions">Reddit Score</th>
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
                      @if (row.lastPrice > 0) {
                        &#36;{{ row.lastPrice | number:'1.2-2' }}
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td
                      class="col-change change-val"
                      [class.positive]="row.priceChange > 0"
                      [class.negative]="row.priceChange < 0"
                    >
                      @if (row.lastPrice > 0) {
                        {{ row.priceChange >= 0 ? '+' : '' }}{{ row.percentChange | number:'1.2-2' }}%
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td class="col-mentions mentions-val">{{ row.mentionCount | number }}</td>
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

  readonly period    = signal<HistoryPeriod>('1mo');
  readonly searchQuery = signal('');
  readonly sortBy    = signal<SortOption>('mentions');

  readonly periods: { value: HistoryPeriod; label: string }[] = [
    { value: '1mo', label: '1 Month' },
    { value: '6mo', label: '6 Months' },
    { value: '1yr', label: '1 Year' },
  ];

  readonly changeLabel = computed(() => {
    switch (this.period()) {
      case '1mo': return '1 Month Change';
      case '6mo': return '6 Month Change';
      case '1yr': return '1 Year Change';
    }
  });

  readonly state = computed(() => this.histService.getState(this.period())());

  readonly filteredRows = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const sort  = this.sortBy();
    let rows = this.state().data.map(toRow);

    if (query) {
      rows = rows.filter(r => r.ticker.toLowerCase().includes(query));
    }

    return [...rows].sort((a, b) => {
      if (sort === 'change') return b.percentChange - a.percentChange;
      return b.mentionCount - a.mentionCount;
    });
  });

  constructor() {
    effect(() => { this.histService.load(this.period()); });
  }
}
