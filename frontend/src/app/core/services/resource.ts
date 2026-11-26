import { Injectable, inject } from '@angular/core';
import {
  Resource,
  ResourceListResponse,
  ApiResourceDetail
} from '../../models/resource.model';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AvailabilityResponse {
  resource_id: number;
  available: boolean;
  reason: string | null;
}

@Injectable({
  providedIn: 'root'
})

export class ResourceService {

  private http = inject(HttpClient);

  private apiUrl = '/api/v1/resources';

  // Temporary sample data until the API is ready.
  private resources: Resource[] = [
    {
      id: 1,
      name: 'Study Room A',
      type: 'Study Room',
      location: 'Library',
      capacity: 8,
      description: 'A quiet study room for individual or group study.'
    },
    {
      id: 2,
      name: 'Computer Lab B',
      type: 'Laboratory',
      location: 'Engineering Building',
      capacity: 24,
      description: 'A computer laboratory for academic work and projects.'
    },
    {
      id: 3,
      name: 'Projector 01',
      type: 'Equipment',
      location: 'Media Center',
      capacity: 1,
      description: 'A projector available for presentations and events.'
    }
  ];

  // Return all sample resources.
  getResources(): Resource[] {
    return this.resources;
  }

  // Return one sample resource by its ID.
  getResourceById(id: number): Resource | undefined {
    return this.resources.find(resource => resource.id === id);
  }

  // Fetch paginated resources from FastAPI.
  getResourcesFromApi(): Observable<ResourceListResponse> {
    return this.http.get<ResourceListResponse>(
      this.apiUrl,
      { withCredentials: true }
    );
  }

  // Check whether a resource is available during a selected interval.
  checkAvailability(
    resourceId: number,
    startTime: string,
    endTime: string
  ): Observable<AvailabilityResponse> {
    return this.http.get<AvailabilityResponse>(
      `${this.apiUrl}/${resourceId}/availability`,
      {
        withCredentials: true,
        params: {
          start_time: startTime,
          end_time: endTime
        }
      }
    );
  }

  // Fetch detailed information about one resource.
  getResourceFromApi(id: number): Observable<ApiResourceDetail> {
    return this.http.get<ApiResourceDetail>(
      `${this.apiUrl}/${id}`,
      { withCredentials: true }
    );
  }

}
