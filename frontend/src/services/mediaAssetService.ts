/**
 * Media Asset Service
 *
 * API service layer for the Media Asset Management admin endpoints.
 * Uses the standard authenticatedGet pattern from apiService.
 *
 * @module services/mediaAssetService
 */

import { authenticatedGet, authenticatedPost, authenticatedPut, buildEndpoint } from './apiService';
import type {
  AssetDashboardData,
  AssetSearchResponse,
  ApproveDeleteResponse,
  UnregisteredObject,
  ImportUnregisteredResponse,
  DeleteUnregisteredResponse,
  RetentionSettingsData,
  UpdateRetentionSettingsResponse,
  DuplicateGroup,
  MergeResult,
} from '@/types/mediaAsset';

/**
 * Fetch asset dashboard summary stats.
 * Requires storage_manage permission (Tenant_Admin role).
 *
 * @returns Dashboard data with totals, storage breakdown, and top orphans
 */
export async function fetchAssetDashboard(): Promise<AssetDashboardData> {
  const response = await authenticatedGet(buildEndpoint('/api/media-assets/dashboard'));

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result.data as AssetDashboardData;
}

/**
 * Trigger an asset reconciliation scan.
 * Returns a scan_id that can be used to subscribe to SSE progress events.
 *
 * @returns Object containing the scan_id
 */
export async function triggerScan(): Promise<{ scan_id: string }> {
  const response = await authenticatedPost(buildEndpoint('/api/media-assets/scan'), {});

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result as { scan_id: string };
}


/**
 * Fetch assets with DELETION_ELIGIBLE status (paginated).
 * Uses the search endpoint with a status filter.
 *
 * @param page - Page number (1-based)
 * @param pageSize - Items per page
 * @returns Paginated search response with deletion-eligible assets
 */
export async function fetchDeletionEligible(page = 1, pageSize = 20): Promise<AssetSearchResponse> {
  const params = new URLSearchParams({
    status: 'DELETION_ELIGIBLE',
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await authenticatedGet(buildEndpoint('/api/media-assets/search', params));

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  return await response.json() as AssetSearchResponse;
}

/**
 * Approve deletion of selected assets.
 * Tenant admin action — permanently deletes the S3 objects and registry records.
 *
 * @param assetIds - Array of asset IDs to approve for deletion
 * @returns Response with deleted/skipped counts and per-asset details
 */
export async function approveDeletion(assetIds: string[]): Promise<ApproveDeleteResponse> {
  const response = await authenticatedPost(buildEndpoint('/api/media-assets/approve-delete'), {
    asset_ids: assetIds,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  return await response.json() as ApproveDeleteResponse;
}


/**
 * Fetch unregistered S3 objects (in S3 but not in registry).
 * Performs a lightweight scan comparing bucket contents against the registry.
 *
 * @returns List of unregistered S3 objects with metadata
 */
export async function fetchUnregistered(): Promise<UnregisteredObject[]> {
  const response = await authenticatedGet(buildEndpoint('/api/media-assets/unregistered'));

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result.data as UnregisteredObject[];
}

/**
 * Import unregistered S3 objects into the asset registry.
 * Creates registry entries for objects that exist in S3 but aren't tracked.
 *
 * @param s3Keys - Array of S3 keys to import
 * @returns Import result with imported/skipped counts
 */
export async function importUnregistered(s3Keys: string[]): Promise<ImportUnregisteredResponse> {
  const response = await authenticatedPost(buildEndpoint('/api/media-assets/import'), {
    s3_keys: s3Keys,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  return await response.json() as ImportUnregisteredResponse;
}

/**
 * Delete unregistered S3 objects permanently.
 * Only deletes objects that are NOT in the registry (safety guard).
 *
 * @param s3Keys - Array of S3 keys to delete
 * @returns Deletion result with deleted/skipped counts
 */
export async function deleteUnregistered(s3Keys: string[]): Promise<DeleteUnregisteredResponse> {
  const response = await authenticatedPost(buildEndpoint('/api/media-assets/delete-unregistered'), {
    s3_keys: s3Keys,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  return await response.json() as DeleteUnregisteredResponse;
}


/**
 * Fetch retention settings per category.
 * Returns current value and source indicator (system_default or tenant_override).
 *
 * @returns Retention settings keyed by category parameter name
 */
export async function fetchRetentionSettings(): Promise<RetentionSettingsData> {
  const response = await authenticatedGet(buildEndpoint('/api/media-assets/retention-settings'));

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result.data as RetentionSettingsData;
}

/**
 * Update retention settings with tenant overrides.
 * Only changed values should be sent.
 *
 * @param overrides - Object mapping category keys to new retention day values
 * @returns Response with list of updated keys
 */
export async function updateRetentionSettings(
  overrides: Record<string, number>
): Promise<UpdateRetentionSettingsResponse> {
  const response = await authenticatedPut(buildEndpoint('/api/media-assets/retention-settings'), overrides);

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  return await response.json() as UpdateRetentionSettingsResponse;
}


/**
 * Fetch duplicate asset groups (assets sharing the same content_hash).
 * Requires storage_manage permission.
 *
 * @returns Array of duplicate groups with their constituent assets
 */
export async function fetchDuplicates(): Promise<DuplicateGroup[]> {
  const response = await authenticatedGet(buildEndpoint('/api/media-assets/duplicates'));

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result.data as DuplicateGroup[];
}

/**
 * Merge duplicate assets — keep one, re-attach references from duplicates, delete duplicates.
 * Requires storage_manage permission.
 *
 * @param keepAssetId - The asset ID to keep
 * @param duplicateAssetIds - Array of duplicate asset IDs to merge into the kept asset
 * @returns Merge result with references_moved and duplicates_deleted counts
 */
export async function mergeDuplicates(
  keepAssetId: string,
  duplicateAssetIds: string[]
): Promise<MergeResult> {
  const response = await authenticatedPost(buildEndpoint('/api/media-assets/merge-duplicates'), {
    keep_asset_id: keepAssetId,
    duplicate_asset_ids: duplicateAssetIds,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.error || `HTTP ${response.status}`);
  }

  const result = await response.json();
  return result as MergeResult;
}
