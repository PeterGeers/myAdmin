/**
 * Landing Page API Service
 *
 * API functions for managing the tenant landing page slug, draft content, and publishing.
 */

import { authenticatedGet, authenticatedPut, authenticatedPost, authenticatedFormData, authenticatedDelete } from './apiService';

// ============================================================================
// Types
// ============================================================================

export interface SlugResponse {
  success: boolean;
  data: {
    slug: string | null;
    administration?: string;
  };
}

export interface SetSlugResponse {
  success: boolean;
  data?: {
    slug: string;
  };
  error?: string;
}

export interface ValidateSlugResponse {
  valid: boolean;
  error?: string;
}

/** Per-block visual settings (Phase A: Look & Feel) */
export interface BlockSettings {
  background_type: "color" | "image" | "gradient";
  background_color: string;
  background_image_key: string;
  background_gradient: string;
  padding: "compact" | "normal" | "spacious";
  text_color: "dark" | "light" | "auto";
  max_width: "contained" | "full-width";
  border_radius: "none" | "sm" | "md" | "lg";
}

/** A single section/block in the landing page */
export interface Section {
  id: string;
  type: string;
  layout: string;
  properties: Record<string, unknown>;
  settings?: BlockSettings; // optional for backwards compatibility
}

export interface DraftResponse {
  success: boolean;
  data: {
    version: number;
    last_modified: string;
    sections: Section[];
  };
}

export interface SaveDraftResponse {
  success: boolean;
  version: number;
  last_modified: string;
}

export interface PublishResponse {
  success: boolean;
  version: number;
  published_at: string;
  public_url: string;
}

export interface UnpublishResponse {
  success: boolean;
  message: string;
}

// ============================================================================
// Slug Management
// ============================================================================

/**
 * Get the current slug for the tenant's landing page.
 */
export async function getSlug(): Promise<SlugResponse> {
  const response = await authenticatedGet('/api/landing/slug');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Set or update the slug for the tenant's landing page.
 */
export async function setSlug(slug: string): Promise<SetSlugResponse> {
  const response = await authenticatedPut('/api/landing/slug', { slug });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Validate a slug for availability and format correctness.
 */
export async function validateSlug(slug: string): Promise<ValidateSlugResponse> {
  const response = await authenticatedPost('/api/landing/slug/validate', { slug });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Draft Management
// ============================================================================

/**
 * Get the current draft for editing.
 */
export async function getDraft(): Promise<DraftResponse> {
  const response = await authenticatedGet('/api/landing/draft');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Save draft (auto-save or manual).
 */
export async function saveDraft(sections: Section[]): Promise<SaveDraftResponse> {
  const response = await authenticatedPut('/api/landing/draft', { sections });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Publishing
// ============================================================================

/**
 * Publish the current draft to S3 (makes it public).
 */
export async function publishLandingPage(): Promise<PublishResponse> {
  const response = await authenticatedPost('/api/landing/publish');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Unpublish the landing page (take offline).
 */
export async function unpublishLandingPage(): Promise<UnpublishResponse> {
  const response = await authenticatedPost('/api/landing/unpublish');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Version History & Rollback (Task 4.1, 4.2)
// ============================================================================

export interface VersionEntry {
  version: number;
  published_at: string;
  published_by: string;
}

export interface VersionsResponse {
  success: boolean;
  data: VersionEntry[];
}

export interface RollbackResponse {
  success: boolean;
  version: number;
  published_at: string;
  public_url: string;
}

/**
 * Get version history for the landing page.
 */
export async function getVersions(): Promise<VersionEntry[]> {
  const response = await authenticatedGet('/api/landing/versions');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  const result: VersionsResponse = await response.json();
  if (!result.success) {
    throw new Error('Failed to load versions');
  }
  return result.data;
}

/**
 * Rollback to a previous version (restores snapshot as draft and re-publishes).
 */
export async function rollbackToVersion(version: number): Promise<RollbackResponse> {
  const response = await authenticatedPost('/api/landing/rollback', { version });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/** Version detail response including sections for preview */
export interface VersionDetailResponse {
  success: boolean;
  data: {
    version: number;
    published_at: string;
    published_by: string;
    sections: Section[];
  };
}

/**
 * Get a specific version's full data including sections (for preview).
 */
export async function getVersionDetail(version: number): Promise<VersionDetailResponse['data']> {
  const response = await authenticatedGet(`/api/landing/version/${version}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  const result: VersionDetailResponse = await response.json();
  if (!result.success) {
    throw new Error('Failed to load version detail');
  }
  return result.data;
}

/**
 * Delete a specific version snapshot.
 */
export async function deleteVersion(version: number): Promise<{ success: boolean; message: string }> {
  const response = await authenticatedDelete(`/api/landing/version/${version}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Branding / Social / SEO Settings (Tasks 3.15, 3.16, 3.17)
// ============================================================================

/** Social media links keyed by platform */
export interface SocialLinks {
  instagram?: string;
  facebook?: string;
  airbnb?: string;
  booking_com?: string;
  linkedin?: string;
  youtube?: string;
  tiktok?: string;
  twitter_x?: string;
}

/** All landing page settings (branding + social + SEO) */
export interface LandingPageSettings {
  // Branding
  company_name: string;
  tagline: string;
  logo_url: string;
  color_primary: string;
  color_accent: string;
  // Contact info
  address: string;
  postal_city: string;
  country: string;
  phone: string;
  email: string;
  coc: string;
  vat: string;
  // SEO
  seo_title: string;
  seo_description: string;
  og_image_url: string;
  // Social
  social_links: SocialLinks;
  show_share_buttons: boolean;
  // Theme (Phase B)
  theme?: { preset: string | null; overrides: Record<string, string> };
  // Typography & Spacing (Phase D)
  font_heading: string;
  font_body: string;
  base_spacing: string;
  border_radius_global: string;
  shadow_style: string;
}

/**
 * Load all landing page branding/social/SEO settings.
 */
export async function getBrandingSettings(): Promise<LandingPageSettings> {
  const response = await authenticatedGet('/api/landing/branding');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  const result = await response.json();
  if (!result.success) {
    throw new Error(result.error || 'Failed to load settings');
  }
  return result.data;
}

/**
 * Save all landing page branding/social/SEO settings.
 */
export async function saveBrandingSettings(settings: Partial<LandingPageSettings>): Promise<void> {
  const response = await authenticatedPut('/api/landing/branding', settings);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  const result = await response.json();
  if (!result.success) {
    throw new Error(result.error || 'Failed to save settings');
  }
}

// ============================================================================
// Image Upload
// ============================================================================

export interface ImageUploadResponse {
  success: boolean;
  data: {
    image_key: string;
    url: string;
  };
  duplicate_of?: { asset_id: string; original_filename: string } | null;
}

/**
 * Upload an image to the public S3 bucket (tenant-scoped).
 *
 * @param file - The image file to upload
 * @param onProgress - Optional progress callback
 * @returns The image key and public URL
 */
export async function uploadImage(
  file: File,
  onProgress?: (progress: { loaded: number; total?: number }) => void,
): Promise<{ image_key: string; url: string; duplicate_of?: { asset_id: string; original_filename: string } | null }> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await authenticatedFormData('/api/landing/images/upload', formData, {
    onUploadProgress: onProgress,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }

  const result: ImageUploadResponse = await response.json();
  if (!result.success) {
    throw new Error('Upload failed');
  }
  return { ...result.data, duplicate_of: result.duplicate_of };
}
