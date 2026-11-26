import { Component, inject } from '@angular/core';
import {
  Router,
  RouterLink,
  RouterLinkActive
} from '@angular/router';
import { Auth } from '../../core/services/auth';

@Component({
  selector: 'app-student-navbar',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './student-navbar.html',
  styleUrl: './student-navbar.css'
})
export class StudentNavbar {

  private auth = inject(Auth);
  private router = inject(Router);

  // Check whether the logged-in user is Staff.
  get isStaff(): boolean {
    return this.auth.user()?.role === 'STAFF';
  }

  isLoggingOut = false;
  logoutError = '';

  logout(): void {
    if (this.isLoggingOut) {
      return;
    }

    this.isLoggingOut = true;
    this.logoutError = '';

    this.auth.logout().subscribe({
      next: () => {
        this.isLoggingOut = false;
        this.router.navigate(['/login']);
      },
      error: () => {
        this.isLoggingOut = false;
        this.logoutError =
          'Unable to log out. Please try again.';
      }
    });
  }
}
