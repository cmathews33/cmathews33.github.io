import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/stock-list/stock-list.component').then(m => m.StockListComponent),
  },
  {
    path: 'historical',
    loadComponent: () =>
      import('./components/history/history.component').then(m => m.HistoryComponent),
  },
  { path: '**', redirectTo: '' },
];
