import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { Auth, UserRole } from './services/auth';

export const authGuard: CanActivateFn = (route) => {

    const auth = inject(Auth);
    const router = inject(Router);

    // Roles allowed to access this route.
    const allowedRoles =
        route.data['roles'] as UserRole[] | undefined;

    // Check whether the user has permission.
    const checkRole = (role: UserRole) => {

        if (!allowedRoles || allowedRoles.includes(role)) {
            return true;
        }

        // Iteration 1 only provides resource pages for Students and Staff.
        // Unauthorized users return to the login page.
        return router.createUrlTree(['/login']);
    };

    // If the user is already loaded, check their role.
    const user = auth.user();

    if (user) {
        return checkRole(user.role);
    }

    // After refreshing, restore the session first.
    return auth.getCurrentUser().pipe(

        map(response => checkRole(response.role)),

        catchError(() => {
            auth.clearSession();

            // No valid session: return to login.
            return of(router.createUrlTree(['/login']));
        })

    );
};
