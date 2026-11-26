import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export type UserRole = 'STUDENT' | 'STAFF' | 'ADMIN';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  id: number;
  full_name: string;
  role: UserRole;
  csrf_token: string;
}

export interface CurrentUserResponse {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  csrf_token: string;
}

export interface AuthenticatedUser {
  id: number;
  full_name: string;
  role: UserRole;
}

@Injectable({
  providedIn: 'root'
})
export class Auth {

  private http = inject(HttpClient);
  private apiUrl = '/api/v1/auth';

  // Keep the CSRF token in memory.
  private csrfToken = '';

  // Track the authenticated user.
  private currentUser = signal<AuthenticatedUser | null>(null);

  // Read the current user without changing it.
  readonly user = this.currentUser.asReadonly();

  // Log in through FastAPI.
  login(data: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(
      `${this.apiUrl}/login`,
      data,
      { withCredentials: true }
    ).pipe(
      tap(response => {
        this.csrfToken = response.csrf_token;

        this.currentUser.set({
          id: response.id,
          full_name: response.full_name,
          role: response.role
        });
      })
    );
  }

  // Restore the session after refreshing the page.
  getCurrentUser(): Observable<CurrentUserResponse> {
    return this.http.get<CurrentUserResponse>(
      `${this.apiUrl}/me`,
      { withCredentials: true }
    ).pipe(
      tap(response => {
        this.csrfToken = response.csrf_token;

        this.currentUser.set({
          id: response.id,
          full_name: response.full_name,
          role: response.role
        });
      })
    );
  }

  // Return the CSRF token for protected requests.
  getCsrfToken(): string {
    return this.csrfToken;
  }

  // Log out through FastAPI and invalidate the session.
  logout(): Observable<void> {
    return this.http.post<void>(
      `${this.apiUrl}/logout`,
      {},
      {
        withCredentials: true,
        headers: {
          'X-CSRF-Token': this.csrfToken
        }
      }
    ).pipe(
      tap(() => {
        // Clear Angular authentication state after successful logout.
        this.clearSession();
      })
    );
  }

  // Clear frontend authentication data.
  clearSession(): void {
    this.csrfToken = '';
    this.currentUser.set(null);
  }

}
