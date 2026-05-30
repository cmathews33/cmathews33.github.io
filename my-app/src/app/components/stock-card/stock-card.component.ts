import { Component, input, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../models/stock.model';
import { formatSource } from '../../utils/ticker-utils';

@Component({
  selector: 'app-stock-card',
  template: `
    <article class="stock-card" [class.positive]="stock().priceChange >= 0" [class.negative]="stock().priceChange < 0">
      <div class="card-header">
        <div>
          <h3 class="ticker">{{ stock().ticker }}</h3>
          <p class="name">{{ stock().name }}</p>
        </div>
        <span
          class="change-badge"
          [class.positive]="stock().priceChange >= 0"
          [class.negative]="stock().priceChange < 0"
        >
          {{ stock().priceChange >= 0 ? '+' : '' }}{{ stock().percentChange | number:'1.2-2' }}%
        </span>
      </div>

      <div class="price-row">
        <span class="price">&#36;{{ stock().price | number:'1.2-2' }}</span>
        <span class="price-change" [class.positive]="stock().priceChange >= 0" [class.negative]="stock().priceChange < 0">
          {{ stock().priceChange >= 0 ? '+' : '' }}{{ stock().priceChange | number:'1.2-2' }}
        </span>
      </div>

      <div class="metrics">
        <div class="metric">
          <span class="metric-label">Mentions</span>
          <span class="metric-value">{{ stock().mentionScore | number }}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Source</span>
          <span class="metric-value">{{ formatSource(stock().source) }}</span>
        </div>
      </div>

      <p class="timestamp">{{ stock().postTimestamp | date:'short' }}</p>
    </article>
  `,
  styleUrls: ['./stock-card.component.css'],
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class StockCardComponent {
  stock = input.required<Stock>();
  protected readonly formatSource = formatSource;
}
