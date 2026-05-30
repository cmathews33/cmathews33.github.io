import { Component, ChangeDetectionStrategy, signal, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StockService } from '../../services/stock.service';
import { formatSource } from '../../utils/ticker-utils';

type SortOption = 'mentions' | 'change' | 'source';

@Component({
  selector: 'app-stock-list',
  template: `
    @if (stockService.isLoading()) {
      <div class="loading-state" role="status" aria-live="polite">
        <div class="spinner" aria-hidden="true"></div>
        <p>Fetching trending data&hellip;</p>
      </div>
    } @else if (stockService.error()) {
      <div class="error-state" role="alert">
        <p>{{ stockService.error() }}</p>
      </div>
    } @else {
      @if (topStock(); as hero) {
        <section class="hero" aria-labelledby="hero-label">
          <div class="hero-inner">
            <p class="hero-label" id="hero-label">TOP RISING STOCK TODAY</p>
            <div class="hero-ticker-row">
              <span class="hero-ticker">{{ hero.ticker }}</span>
              <span
                class="hero-badge"
                [class.positive]="hero.priceChange >= 0"
                [class.negative]="hero.priceChange < 0"
              >
                {{ hero.priceChange >= 0 ? '+' : '' }}{{ hero.percentChange | number:'1.1-1' }}%
              </span>
            </div>
            <p class="hero-subtitle">Trending across social media today</p>
          </div>
        </section>
      }

      <div class="list-wrapper">
        <div class="list-header">
          <div>
            <h2 class="list-title">Harry's Top Rising Stocks</h2>
            <p class="list-subtitle">Trending on Reddit</p>
          </div>
          <div class="refresh-stamps" aria-live="polite">
            @if (stockService.redditRefreshed(); as t) {
              <span class="stamp">Social {{ t | date:'shortTime' }}</span>
            }
            @if (stockService.priceRefreshed(); as t) {
              <span class="stamp">Prices {{ t | date:'shortTime' }}</span>
            }
          </div>
        </div>

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
            <label for="sort-select" class="sort-label">Sort</label>
            <select
              id="sort-select"
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

        <div class="table-wrapper" role="region" aria-label="Rising stocks data">
          <table class="stock-table">
            <thead>
              <tr>
                <th scope="col" class="col-rank">#</th>
                <th scope="col" class="col-ticker">Ticker</th>
                <th scope="col" class="col-name">Company</th>
                <th scope="col" class="col-price">Price</th>
                <th scope="col" class="col-change">24h Change</th>
                <th scope="col" class="col-subreddit">Source</th>
                <th scope="col" class="col-mentions">Mentions</th>
                <th scope="col" class="col-time">Last Post</th>
              </tr>
            </thead>
            <tbody>
              @if (filteredStocks().length > 0) {
                @for (stock of filteredStocks(); track stock.ticker; let i = $index) {
                  <tr class="stock-row">
                    <td class="col-rank rank-num">{{ i + 1 }}</td>
                    <td class="col-ticker">
                      <span class="ticker-sym">{{ stock.ticker }}</span>
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
                    <td class="col-mentions mentions-val">{{ stock.mentionScore | number }}</td>
                    <td class="col-time time-val">{{ stock.postTimestamp | date:'shortTime' }}</td>
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
          Showing {{ filteredStocks().length }} of {{ totalCount() }} stocks
          &bull; Refreshes every 30 min
        </p>
      </div>
    }
  `,
  styleUrls: ['./stock-list.component.css'],
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class StockListComponent {
  readonly stockService = inject(StockService);
  protected readonly formatSource = formatSource;

  readonly searchQuery = signal('');
  readonly sortBy = signal<SortOption>('mentions');

  readonly topStock = computed(() => {
    const stocks = this.stockService.stocksList();
    if (!stocks.length) return null;
    return stocks.reduce(
      (top, s) => (s.mentionScore > top.mentionScore ? s : top),
      stocks[0]
    );
  });

  readonly totalCount = computed(() => this.stockService.stocksList().length);

  readonly filteredStocks = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const sort = this.sortBy();
    let stocks = this.stockService.stocksList();

    if (query) {
      stocks = stocks.filter(
        s =>
          s.ticker.toLowerCase().includes(query) ||
          s.name.toLowerCase().includes(query)
      );
    }

    return [...stocks].sort((a, b) => {
      switch (sort) {
        case 'change':
          return b.percentChange - a.percentChange;
        case 'source':
          return a.source.localeCompare(b.source);
        default:
          return b.mentionScore - a.mentionScore;
      }
    });
  });

}
