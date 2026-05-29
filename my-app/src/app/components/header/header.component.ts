import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { NgOptimizedImage } from '@angular/common';

@Component({
  selector: 'app-header',
  template: `
    <header class="header">
      <div class="header-inner">
        <div class="brand">
          <img ngSrc="harryimg.png" alt="Harry's Risers" width="48" height="48" class="brand-logo" />
        </div>
        <span class="brand-tagline">Discover what Reddit is talking about</span>
        <nav class="nav" role="navigation" aria-label="Main navigation">
          <a
            routerLink="/"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            #homeLink="routerLinkActive"
            class="nav-link"
            [attr.aria-current]="homeLink.isActive ? 'page' : null"
          >Home</a>
          <a
            routerLink="/historical"
            routerLinkActive="active"
            #histLink="routerLinkActive"
            class="nav-link"
            [attr.aria-current]="histLink.isActive ? 'page' : null"
          >Historical</a>
          <a href="#" class="nav-link">Watchlist</a>
        </nav>
      </div>
    </header>
  `,
  styleUrls: ['./header.component.css'],
  imports: [RouterLink, RouterLinkActive, NgOptimizedImage],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'banner' },
})
export class HeaderComponent {}
