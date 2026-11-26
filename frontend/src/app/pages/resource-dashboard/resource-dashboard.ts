import { Component, inject, OnInit, ChangeDetectorRef } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ResourceService } from '../../core/services/resource';
import { Resource } from '../../models/resource.model';
import { FormsModule } from '@angular/forms';
import { Auth } from '../../core/services/auth';
import { StudentNavbar } from '../../shared/student-navbar/student-navbar';

@Component({
  selector: 'app-resource-dashboard',
  imports: [RouterLink, FormsModule, StudentNavbar],
  templateUrl: './resource-dashboard.html',
  styleUrl: './resource-dashboard.css'
})
export class ResourceDashboard implements OnInit {

  // Indicates whether resources are currently loading.
  // Will be connected to the real API later.
  isLoading = false;

  // Stores a resource loading error.
  // Empty means no error.
  errorMessage = '';

  // Stores the text entered in the search bar.
  searchTerm = '';

  matchesSearch(resource: Resource): boolean {
    const search = this.searchTerm.trim().toLowerCase();

    if (!search) {
      return true;
    }

    return (
      resource.name.toLowerCase().includes(search) ||
      resource.location.toLowerCase().includes(search)
    );
  }

  private resourceService = inject(ResourceService);

  private cdr = inject(ChangeDetectorRef);

  // Resources loaded from FastAPI.
  resources: Resource[] = [];

  // Load resources when the dashboard opens.
  ngOnInit(): void {
    this.loadResources();
  }

  // Retrieve real resources from FastAPI.
  loadResources(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.resourceService.getResourcesFromApi().subscribe({

      next: (response) => {

        // Convert backend resources to our frontend model.
        this.resources = response.items.map(resource => ({
          id: resource.id,
          name: resource.name,
          type:
            resource.type === 'STUDY_ROOM' ? 'Study Room' :
              resource.type === 'LAB' ? 'Laboratory' :
                resource.type === 'MEETING_ROOM' ? 'Meeting Room' :
                  resource.type === 'EQUIPMENT' ? 'Equipment' :
                    resource.type,
          location: resource.location ?? '',
          capacity: resource.capacity ?? 0,

          // Descriptions are provided by the detail endpoint.
          description: ''
        }));

        this.isLoading = false;

        // Notify Angular that the API data is ready.
        this.cdr.markForCheck();
      },

      error: (error) => {
        this.isLoading = false;
        this.resources = [];

        if (error.status === 0) {
          this.errorMessage =
            'Cannot connect to the server. Please try again.';
        } else if (error.status === 401) {
          this.errorMessage =
            'Your session has expired. Please log in again.';
        } else {
          this.errorMessage =
            'Unable to load campus resources. Please try again.';
        }
        // Update the UI when the API request fails.
        this.cdr.markForCheck();
      }

    });
  }

  private auth = inject(Auth);
  private router = inject(Router);

  // Tracks the logout request.
  isLoggingOut = false;

  // Displays an error if logout fails.
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

        // FastAPI has invalidated the session.
        // Return the user to the login page.
        this.router.navigate(['/login']);
      },

      error: () => {
        this.isLoggingOut = false;
        this.logoutError =
          'Unable to log out. Please try again.';
      }
    });
  }

  selectedCategory = 'All';

  // Update the selected category.
  selectCategory(category: string): void {
    this.selectedCategory = category;
  }

  // Filter resources by category.
  get filteredResources(): Resource[] {
    return this.resources.filter(resource => {

      // Check the selected category.
      const matchesCategory =
        this.selectedCategory === 'All' ||
        resource.type === this.selectedCategory;

      // Check the search text.
      const matchesSearch = this.matchesSearch(resource);

      // Resource must match both conditions.
      return matchesCategory && matchesSearch;

    });
  }
}
