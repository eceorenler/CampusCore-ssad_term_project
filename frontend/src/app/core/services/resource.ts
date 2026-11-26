import { Injectable, inject } from '@angular/core';
import {
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
