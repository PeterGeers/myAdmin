/**
 * Parameter-driven configuration type definitions.
 */

export interface Parameter {
  id: number | null;
  namespace: string;
  key: string;
  value: string | number | boolean | Record<string, unknown> | unknown[];
  value_type: 'string' | 'number' | 'boolean' | 'json';
  scope_origin: 'system' | 'tenant' | 'role' | 'user';
  is_secret: boolean;
  has_code_default?: boolean;
}

export interface ParameterCreateRequest {
  scope: 'system' | 'tenant';
  namespace: string;
  key: string;
  value: string | number | boolean | Record<string, unknown> | unknown[];
  value_type: 'string' | 'number' | 'boolean' | 'json';
  is_secret: boolean;
}

export interface ParameterUpdateRequest {
  value: string | number | boolean | Record<string, unknown> | unknown[];
  value_type?: 'string' | 'number' | 'boolean' | 'json';
}

export interface ParameterDefaultResponse {
  success: boolean;
  has_default: boolean;
  value?: string | number | boolean | Record<string, unknown> | unknown[];
  value_type?: 'string' | 'number' | 'boolean' | 'json';
  source?: 'code_default' | 'system';
}

export interface ParametersResponse {
  success: boolean;
  tenant: string;
  parameters: Record<string, Parameter[]>;
}

/** Response shape for parameter create/update/delete mutations. */
export interface ParameterMutationResponse {
  success: boolean;
  error?: string;
  /** Present on create: the id of the newly created parameter row. */
  id?: number;
  /**
   * Projection DELIVERY status for a tenant-scope config write (reliability):
   * `true` = the change was projected to DynamoDB and the module will read it;
   * `false` = the write was SAVED but projection FAILED (see `projection_error`) —
   * the change is persisted in MySQL but not yet live to the module; `null`/absent =
   * not applicable (non-tenant scope / older backend).
   */
  projected?: boolean | null;
  /** Human-readable reason a projection failed (only when `projected === false`). */
  projection_error?: string;
}
