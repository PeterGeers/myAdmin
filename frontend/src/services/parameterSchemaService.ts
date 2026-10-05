import { ParameterSchemaResponse } from '../types/parameterSchemaTypes';
import { authenticatedGet, buildEndpoint } from './apiService';

export async function getParameterSchema(): Promise<ParameterSchemaResponse> {
  const resp = await authenticatedGet(buildEndpoint('/api/tenant-admin/parameters/schema'));
  return resp.json();
}
