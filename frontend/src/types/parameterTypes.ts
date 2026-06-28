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
