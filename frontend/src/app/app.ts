import { Component, inject, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { Auth } from './core/services/auth';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements OnInit {

  private auth = inject(Auth);

  ngOnInit(): void {

    // Check whether the browser has an active session.
    this.auth.getCurrentUser().subscribe({

      next: () => {
        // The Auth service automatically restores the CSRF token.
        console.log('Existing session restored.');
      },

      error: (error: HttpErrorResponse) => {
        if (error.status === 401) {
          // This is normal when the user has not logged in.
          console.log('No active login session.');
        } else {
          console.error('Session check failed:', error.status);
        }
      }

    });

  }

}
