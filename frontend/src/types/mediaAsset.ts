/**
 * Media Asset type definitions
 *
 * Types for the Media Asset Management system (Asset Picker, Asset Administration).
 * Corresponds to the backend `s3_assets` table and API response shapes.
 */

export type AssetCategory = 'invoices' | 'branding' | 'templates' | 'landing-pages';

export type AssetMediaType = 'image' | 'video' | 'document';

export type AssetSortField = 'created_at' | 'original_filename' | 'file_size' | 'reference_count';

export type SortOrder = 'asc' | 'desc';

/**
 * A media asset as returned by GET /api/assets/search
 */
export interface MediaAsset {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  category: AssetCategory;
  media_type: AssetMediaType;
  created_at: string;
  reference_count: number;
  presigned_url: string | null;
}

/**
 * Search filter parameters for the asset search API
 */
export interface AssetSearchFilters {
  q?: string;
  category?: AssetCategory | '';
  media_type?: AssetMediaType | '';
  sort?: AssetSortField;
  order?: SortOrder;
  page?: number;
  page_size?: number;
}

/**
 * Pagination metadata from search response
 */
export interface AssetPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/**
 * Full search API response shape
 */
export interface AssetSearchResponse {
  success: boolean;
  data: MediaAsset[];
  pagination: AssetPagination;
}

/** Info about a duplicate asset detected during upload */
export interface DuplicateInfo {
  asset_id: string;
  original_filename: string;
}

/** Dashboard summary data from GET /api/assets/dashboard */
export interface AssetDashboardData {
  total_assets: number;
  active_assets: number;
  orphaned_assets: number;
  deletion_eligible: number;
  storage_by_category: Record<string, { count: number; bytes: number }>;
  last_scan_at: string | null;
  top_orphans: Array<{
    id: string;
    filename: string;
    size: number;
    days_orphaned: number;
  }>;
}

/** Response from POST /api/assets/approve-delete */
export interface ApproveDeleteResponse {
  success: boolean;
  deleted: number;
  skipped: number;
  details: Array<{ asset_id: string; status: 'deleted' | 'skipped'; reason?: string }>;
}

/** Scan progress phases from SSE stream */
export type ScanPhase =
  | 'scanning_s3'
  | 'checking_registry'
  | 'verifying_references'
  | 'transitioning'
  | 'complete';

/** SSE event data from GET /api/assets/scan/{scan_id}/status */
export interface ScanProgress {
  phase: ScanPhase;
  progress?: number;
  summary?: ScanSummary;
}

/** Summary returned when scan phase = 'complete' */
export interface ScanSummary {
  total_assets: number;
  consistent: number;
  unregistered: number;
  missing: number;
  stale_references: number;
  newly_eligible: number;
}

/** An S3 object not registered in the asset registry */
export interface UnregisteredObject {
  s3_key: string;
  bucket: string;
  size: number;
  last_modified: string | null;
}

/** Response from POST /api/assets/import (importing unregistered objects) */
export interface ImportUnregisteredResponse {
  success: boolean;
  imported: number;
  skipped: number;
}

/** Response from POST /api/assets/delete-unregistered */
export interface DeleteUnregisteredResponse {
  success: boolean;
  deleted: number;
  skipped: number;
}

/** A single retention setting value with source indicator */
export interface RetentionSettingValue {
  value: number;
  source: 'system_default' | 'tenant_override';
}

/** Retention settings data — one entry per category key */
export type RetentionSettingsData = Record<string, RetentionSettingValue>;

/** Response from PUT /api/assets/retention-settings */
export interface UpdateRetentionSettingsResponse {
  success: boolean;
  updated: string[];
}

/** A duplicate asset within a group sharing the same content hash */
export interface DuplicateAsset {
  id: string;
  original_filename: string;
  file_size: number;
  category: AssetCategory;
  reference_count: number;
  created_at: string;
}

/** A group of assets sharing the same content_hash */
export interface DuplicateGroup {
  content_hash: string;
  assets: DuplicateAsset[];
}

/** Response from POST /api/assets/merge-duplicates */
export interface MergeResult {
  references_moved: number;
  duplicates_deleted: number;
}
