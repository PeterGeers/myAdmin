/**
 * API service for ZZP field configuration (visibility/required per entity).
 */
import { authenticatedGet, authenticatedPut, buildEndpoint } from './apiService';
import { FieldConfig } from '../types/zzp';

const BASE = '/api/zzp/field-config';

export async function getFieldConfig(entity: string): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${entity}`));
  return resp.json();
}

export async function updateFieldConfig(entity: string, config: FieldConfig): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${entity}`), config);
  return resp.json();
}
