import { Component, ChangeDetectionStrategy, signal, computed, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HistoryService, HistoryPeriod } from '../../services/history.service';
import { formatSource } from '../../utils/ticker-utils';

type SortOption = 'mentions' | 'change' | 'source';

@Component({
  selector: 'app-history',
  template: `
    <div class="page-header">
      <div class="page-header-inner">
        <div>
          <h1 class="page-title">Historical Trends</h1>
          <p class="page-sub">Trending on StockTwits &amp; Reddit with historical price performance</p>
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
    } @else if (state().stocks.length === 0) {
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
              placeholder="Search tickers or companies..."
              aria-label="Search stocks by ticker or company name"
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
              <option value="source">By Source</option>
            </select>
          </div>
        </div>

        <div class="table-wrapper" role="region" aria-label="Historical stocks data">
          <table class="stock-table">
            <thead>
              <tr>
                <th scope="col" class="col-rank">#</th>
                <th scope="col" class="col-ticker">Ticker</th>
                <th scope="col" class="col-name">Company</th>
                <th scope="col" class="col-price">Price</th>
                <th scope="col" class="col-change">{{ changeLabel() }}</th>
                <th scope="col" class="col-subreddit">Source</th>
                <th scope="col" class="col-mentions">Reddit Mentions</th>
                <th scope="col" class="col-time">Top Post</th>
              </tr>
            </thead>
            <tbody>
              @if (filteredStocks().length > 0) {
                @for (stock of filteredStocks(); track stock.ticker; let i = $index) {
                  <tr class="stock-row">
                    <td class="col-rank rank-num">{{ i + 1 }}</td>
                    <td class="col-ticker">
                      <div class="ticker-cell">
                        <span
                          class="ticker-dot"
                          [class.dot-positive]="stock.sentiment === 'positive'"
                          [class.dot-negative]="stock.sentiment === 'negative'"
                          [class.dot-neutral]="stock.sentiment === 'neutral'"
                          [attr.aria-label]="stock.sentiment + ' sentiment'"
                        ></span>
                        <span class="ticker-sym">{{ stock.ticker }}</span>
                      </div>
                    </td>
                    <td class="col-name company-name">{{ stock.name }}</td>
                    <td class="col-price price-val">
                      @if (stock.price > 0) {
                        &#36;{{ stock.price | number:'1.2-2' }}
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td
                      class="col-change change-val"
                      [class.positive]="stock.priceChange > 0"
                      [class.negative]="stock.priceChange < 0"
                    >
                      @if (stock.price > 0) {
                        {{ stock.priceChange >= 0 ? '+' : '' }}{{ stock.percentChange | number:'1.2-2' }}%
                      } @else {
                        <span class="na">—</span>
                      }
                    </td>
                    <td class="col-subreddit subreddit-val">{{ formatSource(stock.source) }}</td>
                    <td class="col-mentions mentions-val">{{ stock.commentCount | number }}</td>
                    <td class="col-time time-val">{{ stock.timestamp | date:'mediumDate' }}</td>
                  </tr>
                }
              } @else {
                <tr>
                  <td colspan="8" class="no-results">No stocks match your search.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <p class="results-count">
          Showing {{ filteredStocks().length }} of {{ state().stocks.length }} stocks
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
  protected readonly formatSource = formatSource;

  readonly period = signal<HistoryPeriod>('1mo');
  readonly searchQuery = signal('');
  readonly sortBy = signal<SortOption>('mentions');

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

  readonly filteredStocks = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const sort = this.sortBy();
    let stocks = this.state().stocks;

    if (query) {
      stocks = stocks.filter(
        s => s.ticker.toLowerCase().includes(query) || s.name.toLowerCase().includes(query)
      );
    }

    return [...stocks].sort((a, b) => {
      switch (sort) {
        case 'change':    return b.percentChange - a.percentChange;
        case 'source':    return a.source.localeCompare(b.source);
        default:          return b.commentCount - a.commentCount;
      }
    });
  });

  constructor() {
    effect(() => { this.histService.load(this.period()); });
  }
}
