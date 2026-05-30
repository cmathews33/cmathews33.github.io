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
  {
    path: 'logic',
    loadComponent: () =>
      import('./components/logic/logic.component').then(m => m.LogicComponent),
  },
  { path: '**', redirectTo: '' },
];
