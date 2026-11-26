import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { Auth, UserRole } from './services/auth';

export const guestGuard: CanActivateFn = () => {

    const auth = inject(Auth);
    const router = inject(Router);

    // Iteration 1 redirects Students and Staff to resources.
    const redirectByRole = (role: UserRole) => {

        if (role === 'STUDENT' || role === 'STAFF') {
            return router.createUrlTree(['/resources']);
        }

        // Admin management is not included in Iteration 1.
        // Allow Admin users to remain on the login page.
        return true;
    };

    // Check the user already stored in Angular.
    const user = auth.user();

    if (user) {
        return redirectByRole(user.role);
    }

    // Restore any existing session.
    return auth.getCurrentUser().pipe(

        map(response => redirectByRole(response.role)),

        catchError(() => {
            // No active session: allow access to Login.
            return of(true);
        })

    );
};
