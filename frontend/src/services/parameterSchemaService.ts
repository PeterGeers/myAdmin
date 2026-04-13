import { authenticatedGet, buildEndpoint } from './apiService';
import { ParameterSchemaResponse } from '../types/parameterSchemaTypes';

export async function getParameterSchema(): Promise<ParameterSchemaResponse> {
  const resp = await authenticatedGet(buildEndpoint('/api/tenant-admin/parameters/schema'));
  return resp.json();
}
