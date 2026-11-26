export interface Resource {
  id: number;
  name: string;
  type: string;
  location: string;
  capacity: number;
  description: string;
}

export interface ApiResourceSummary {
  id: number;
  name: string;
  type: string;
  location: string | null;
  capacity: number | null;
  is_active: boolean;
}

export interface ApiResourceDetail extends ApiResourceSummary {
  description: string | null;
  opens_at: string;
  closes_at: string;
}

export interface ResourceListResponse {
  items: ApiResourceSummary[];
  page: number;
  page_size: number;
  total: number;
}
