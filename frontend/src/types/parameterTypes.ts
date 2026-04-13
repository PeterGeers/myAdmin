/**
 * Parameter-driven configuration type definitions.
 */

export interface Parameter {
  id: number | null;
  namespace: string;
  key: string;
  value: any;
  value_type: 'string' | 'number' | 'boolean' | 'json';
  scope_origin: 'system' | 'tenant' | 'role' | 'user';
  is_secret: boolean;
}

export interface ParameterCreateRequest {
  scope: 'system' | 'tenant';
  namespace: string;
  key: string;
  value: any;
  value_type: 'string' | 'number' | 'boolean' | 'json';
  is_secret: boolean;
}

export interface ParameterUpdateRequest {
  value: any;
  value_type?: 'string' | 'number' | 'boolean' | 'json';
}

export interface ParametersResponse {
  success: boolean;
  tenant: string;
  parameters: Record<string, Parameter[]>;
}
