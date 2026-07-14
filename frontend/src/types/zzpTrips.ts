// ZZP Rittenregistratie TypeScript Types
// Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.6

export interface Vehicle {
  id: number;
  license_plate: string;
  make: string | null;
  model: string | null;
  year_built: number | null;
  vin: string | null;
  vehicle_type: 'private_for_business' | 'business';
  odometer_unit: 'km' | 'miles';
  owner_lease_company: string | null;
  start_odometer: number;
  start_date: string;
  is_active: boolean;
}

export interface Trip {
  id: number;
  vehicle_id: number;
  trip_date: string;
  start_time: string | null;
  end_time: string | null;
  start_address: string;
  end_address: string;
  start_odometer: number;
  end_odometer: number;
  distance_km: number;
  trip_category: string;
  trip_purpose: string;
  route_description: string | null;
  contact_id: number | null;
  contact?: { id: number; company_name: string };
  project_name: string | null;
  notes: string | null;
  is_billable: boolean;
  is_billed: boolean;
  invoice_id: number | null;
  is_gap_fill: boolean;
  is_cancelled: boolean;
  version: number;
}

export interface RoutePreset {
  id: number;
  from_address: string;
  to_address: string;
  default_category: string | null;
  default_purpose: string | null;
  contact_id: number | null;
  typical_distance_km: number | null;
  use_count: number;
  is_manual: boolean;
}

export interface TripSummary {
  year: number;
  vehicle_id: number;
  total_km: number;
  zakelijk_km: number;
  prive_km: number;
  woonwerk_km: number;
  bijtelling_km: number;
  bijtelling_limit: number;
  bijtelling_warning: boolean;
  tax_deduction: number;
}

export interface TripFilters {
  vehicle_id?: number;
  date_from?: string;
  date_to?: string;
  trip_category?: string;
  contact_id?: number;
  is_billed?: boolean;
  is_gap_fill?: boolean;
  limit?: number;
  offset?: number;
}

export interface GapFillData {
  vehicle_id: number;
  trip_date: string;
  start_odometer: number;
  end_odometer: number;
  start_address: string;
  end_address: string;
  trip_category: string;
  trip_purpose: string;
}

export interface TripAuditEntry {
  id: number;
  trip_id: number;
  version: number;
  action: 'created' | 'updated' | 'cancelled';
  changed_fields: Record<string, { old: unknown; new: unknown }> | null;
  correction_reason: string | null;
  changed_by: string;
  changed_at: string;
}

export interface ImportRow {
  row_number: number;
  trip_date: string;
  start_address: string;
  end_address: string;
  start_odometer: number;
  end_odometer: number;
  trip_category?: string;
  trip_purpose?: string;
  contact_name?: string;
  notes?: string;
  status: 'ok' | 'warning' | 'error';
  messages: string[];
}
