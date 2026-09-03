/**
 * API service for ZZP field configuration (visibility/required per entity).
 */
import { authenticatedGet, authenticatedPut, buildEndpoint } from './apiService';
import { FieldConfig } from '../types/zzp';

const BASE = '/api/zzp/field-config';

/** Response containing the field configuration for an entity. */
interface FieldConfigResponse {
  success: boolean;
  error?: string;
  data: FieldConfig;
}

/** Response for a field configuration update. */
interface FieldConfigUpdateResponse {
  success: boolean;
  error?: string;
}

export async function getFieldConfig(entity: string): Promise<FieldConfigResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${entity}`));
  return resp.json();
}

export async function updateFieldConfig(entity: string, config: FieldConfig): Promise<FieldConfigUpdateResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${entity}`), config);
  return resp.json();
}
