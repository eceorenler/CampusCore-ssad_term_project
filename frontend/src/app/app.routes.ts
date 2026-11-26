import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { guestGuard } from './core/guest.guard';
import { Login } from './pages/login/login';
import { ResourceDashboard } from './pages/resource-dashboard/resource-dashboard';
import { ResourceDetails } from './pages/resource-details/resource-details';

export const routes: Routes = [
    {
        path: 'login',
        component: Login,
        canActivate: [guestGuard]
    },
    {
        path: 'resources',
        component: ResourceDashboard,
        canActivate: [authGuard],
        data: { roles: ['STUDENT', 'STAFF'] }
    },
    {
        path: 'resources/:id',
        component: ResourceDetails,
        canActivate: [authGuard],
        data: { roles: ['STUDENT', 'STAFF'] }
    },
    {
        path: '',
        redirectTo: 'login',
        pathMatch: 'full'
    },
    {
        path: '**',
        redirectTo: 'login'
    }
];
