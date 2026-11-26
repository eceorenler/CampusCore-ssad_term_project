import { Component, inject, ChangeDetectorRef } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Auth } from '../../core/services/auth';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './login.html',
  styleUrl: './login.css'
})
export class Login {

  private fb = inject(FormBuilder);
  private auth = inject(Auth);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  // Login form
  loginForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required]
  });

  // Login feedback
  isLoading = false;
  loginError = '';

  onLogin(): void {
    this.loginError = '';

    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }

    this.isLoading = true;

    this.auth.login(this.loginForm.getRawValue()).subscribe({
      next: (response) => {
        this.isLoading = false;

        // Navigate according to the authenticated user's role.
        switch (response.role) {
          case 'STUDENT':
          case 'STAFF':
            this.router.navigate(['/resources']);
            break;

          case 'ADMIN':
            // Admin management is not available in Iteration 1.
            // End the authenticated session safely.
            this.auth.logout().subscribe({
              next: () => {
                this.loginError =
                  'Admin features will be available in Iteration 2.';
                this.cdr.markForCheck();
              },
              error: () => {
                this.loginError =
                  'Admin access is not available in this version. ' +
                  'Your session could not be closed. Please try again later.';
                this.cdr.markForCheck();
              }
            });
            break;

          default:
            this.loginError = 'Your account has an unsupported role.';
        }

        this.cdr.markForCheck();

      },

      error: (error: HttpErrorResponse) => {
        this.isLoading = false;

        // Display an appropriate authentication error.
        if (error.status === 0) {
          this.loginError = 'Cannot connect to the server. Please try again.';
        } else if (error.status === 401) {
          this.loginError = 'Invalid email or password.';
        } else if (error.status === 429) {
          this.loginError = 'Too many login attempts. Please try again later.';
        } else {
          this.loginError =
            error.error?.error?.message || 'Login failed. Please try again.';
        }

        this.cdr.markForCheck();

      }
    });
  }
}
