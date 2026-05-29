import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';

@Component({
  selector: 'app-root',
  template: `
    <app-header></app-header>
    <main role="main">
      <router-outlet></router-outlet>
    </main>
  `,
  styleUrls: ['./app-styles.css'],
  imports: [HeaderComponent, RouterOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {}
