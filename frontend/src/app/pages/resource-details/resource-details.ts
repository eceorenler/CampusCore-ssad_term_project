import { Component, inject, ChangeDetectorRef } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ResourceService } from '../../core/services/resource';
import { Resource } from '../../models/resource.model';
import { StudentNavbar } from '../../shared/student-navbar/student-navbar';

@Component({
  selector: 'app-resource-details',
  imports: [RouterLink, ReactiveFormsModule, StudentNavbar],
  templateUrl: './resource-details.html',
  styleUrl: './resource-details.css'
})
export class ResourceDetails {

  // Resource information and loading state
  resource: Resource | undefined;
  isLoading = false;
  resourceLoadError = '';

  // Opening hours returned by FastAPI
  opensAt = '';
  closesAt = '';

  private route = inject(ActivatedRoute);
  private resourceService = inject(ResourceService);
  private cdr = inject(ChangeDetectorRef);
  private fb = inject(FormBuilder);

  // User-selected time interval
  availabilityForm = this.fb.nonNullable.group({
    date: ['', Validators.required],
    startTime: ['', Validators.required],
    endTime: ['', Validators.required]
  });

  // Availability check feedback
  isCheckingAvailability = false;
  availabilityResult: boolean | null = null;
  availabilityMessage = '';

  checkAvailability(): void {
    this.availabilityResult = null;
    this.availabilityMessage = '';

    if (this.isCheckingAvailability) {
      return;
    }

    if (this.availabilityForm.invalid) {
      this.availabilityForm.markAllAsTouched();
      this.availabilityMessage = 'Please complete all fields.';
      return;
    }

    if (!this.resource) {
      this.availabilityMessage = 'Resource not found.';
      return;
    }

    const { date, startTime, endTime } =
      this.availabilityForm.getRawValue();

    const start = new Date(`${date}T${startTime}`);
    const end = new Date(`${date}T${endTime}`);

    if (
      Number.isNaN(start.getTime()) ||
      Number.isNaN(end.getTime()) ||
      start <= new Date()
    ) {
      this.availabilityMessage =
        'Please select a valid future date and time.';
      return;
    }

    if (end <= start) {
      this.availabilityMessage =
        'End time must be after start time.';
      return;
    }

    if ((end.getTime() - start.getTime()) / 60000 > 120) {
      this.availabilityMessage =
        'The selected interval cannot exceed 120 minutes.';
      return;
    }

    this.isCheckingAvailability = true;

    // Convert local dates to timezone-aware ISO timestamps.
    const startIso = start.toISOString();
    const endIso = end.toISOString();

    this.resourceService.checkAvailability(
      this.resource.id,
      startIso,
      endIso
    ).subscribe({
      next: (response) => {
        this.isCheckingAvailability = false;
        this.availabilityResult = response.available;

        this.availabilityMessage = response.available
          ? 'This resource is available during the selected time.'
          : 'This resource is unavailable during the selected time.';

        this.cdr.markForCheck();
      },
      error: () => {
        this.isCheckingAvailability = false;
        this.availabilityResult = null;
        this.availabilityMessage =
          'Unable to check availability. Please try again.';

        this.cdr.markForCheck();
      }
    });
  }

  constructor() {

    // Read the resource ID from the URL
    this.route.paramMap.subscribe(params => {
      const id = Number(params.get('id'));

      // Clear previously displayed resource information
      this.resource = undefined;
      this.resourceLoadError = '';
      this.opensAt = '';
      this.closesAt = '';

      if (!Number.isInteger(id) || id <= 0) {
        this.isLoading = false;
        this.resourceLoadError = 'Invalid resource ID.';
        this.cdr.markForCheck();
        return;
      }

      this.isLoading = true;

      // Fetch real resource details from FastAPI
      this.resourceService.getResourceFromApi(id).subscribe({

        next: (response) => {

          // Convert backend data into the frontend model
          this.resource = {
            id: response.id,
            name: response.name,
            type:
              response.type === 'STUDY_ROOM' ? 'Study Room' :
                response.type === 'LAB' ? 'Laboratory' :
                  response.type === 'MEETING_ROOM' ? 'Meeting Room' :
                    response.type === 'EQUIPMENT' ? 'Equipment' :
                      response.type,
            location: response.location ?? '',
            capacity: response.capacity ?? 0,
            description: response.description ?? ''
          };

          // Store the resource's opening hours
          this.opensAt = response.opens_at ?? '';
          this.closesAt = response.closes_at ?? '';

          this.isLoading = false;
          this.cdr.markForCheck();
        },

        error: (error) => {
          this.isLoading = false;
          this.resource = undefined;

          if (error.status === 404) {
            this.resourceLoadError = 'Resource not found.';
          } else if (error.status === 401) {
            this.resourceLoadError =
              'Your session has expired. Please log in again.';
          } else {
            this.resourceLoadError =
              'Unable to load resource details. Please try again.';
          }

          this.cdr.markForCheck();
        }

      });
    });
  }
}
